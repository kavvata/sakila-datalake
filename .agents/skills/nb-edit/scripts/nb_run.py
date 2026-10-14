#!/usr/bin/env python3
"""Execute notebook cells on the docker-compose Jupyter server.

Connects to a Jupyter server (expects a jupyter container in this project's
compose; default http://localhost:8888, token disabled), starts a `python3` kernel, executes the notebook's code cells one by one,
and reports per-cell status/outputs. The kernel runs inside the compose
Jupyter container, so it has the same Spark environment and the repo mount
at /workspace.

Wire protocol (jupyter_server 2.x, no subprotocol): one JSON object per
websocket frame: {"channel": "shell"|"iopub"|..., "header": {...},
"parent_header": {...}, "msg_id": ..., "metadata": {...}, "content": {...},
"buffers": []}.

Usage (from the repo root):

    uv run python .agents/skills/nb-edit/scripts/nb_run.py <nb.ipynb> [options]

Options:
    --url URL             server URL (default http://localhost:8888)
    --token TOKEN         auth token (default: $JUPYTER_TOKEN or cookie/xsrf flow)
    --python-path PATH    prepend to sys.path in the kernel before cell 0
                          (default /workspace/scripts, "" to disable)
    --cell N              only run this cell index (repeatable; 0-based,
                          negative ok). Default: all code cells
    --timeout SECONDS     per-cell timeout (default 300)
    --write               write collected outputs back into the .ipynb
    --keep-kernel         do not shut the kernel down afterwards
"""
from __future__ import annotations

import argparse
import datetime
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import nbformat
import websocket  # websocket-client

VERSION = "5.3"
SESSION_ID = str(uuid.uuid4())


class Server:
    def __init__(self, url: str, token: str | None):
        self.url = url.rstrip("/")
        self.token = token
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.xsrf: str | None = None
        if not self.token:
            # even a 404 GET sets the _xsrf cookie (and anonymous session)
            try:
                self.op.open(f"{self.url}/login", timeout=10)
            except urllib.error.HTTPError:
                pass
            self.xsrf = next((c.value for c in self.jar if c.name == "_xsrf"), None)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Token {self.token}"
        if self.xsrf:
            h["X-XSRFToken"] = self.xsrf
        return h

    def api(self, method: str, path: str, body: dict | None = None, timeout: int = 30):
        url = f"{self.url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with self.op.open(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise SystemExit(f"error: {method} {path} -> HTTP {e.code}: {e.read()[:300]!r}")

    def start_kernel(self) -> str:
        k = self.api("POST", "/api/kernels", {"name": "python3"})
        if not k or "id" not in k:
            raise SystemExit(f"error: unexpected /api/kernels response: {k!r}")
        return k["id"]

    def wait_idle(self, kid: str, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            k = self.api("GET", f"/api/kernels/{kid}")
            if k and k.get("execution_state") == "idle":
                return
            time.sleep(0.5)
        raise SystemExit("error: kernel did not become idle")

    def stop_kernel(self, kid: str) -> None:
        try:
            self.api("DELETE", f"/api/kernels/{kid}")
        except SystemExit as e:
            print(f"warning: could not stop kernel {kid}: {e}", file=sys.stderr)

    def ws_url(self, kid: str) -> str:
        base = self.url.replace("https://", "wss://").replace("http://", "ws://")
        extra = f"?token={self.token}" if self.token else ""
        return f"{base}/api/kernels/{kid}/channels{extra}"


def jmsg(channel: str, msg_type: str, content: dict, parent_header: dict | None = None) -> str:
    mid = str(uuid.uuid4())
    msg = {
        "channel": channel,
        "header": {
            "msg_id": mid,
            "session": SESSION_ID,
            "username": "nb-run",
            "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "msg_type": msg_type,
            "version": VERSION,
        },
        "parent_header": parent_header or {},
        "msg_id": mid,
        "metadata": {},
        "content": content,
    }
    return json.dumps(msg)


def to_nb_output(msg: dict) -> dict | None:
    """Convert an iopub/shell message to an nbformat output (or None)."""
    t = msg["header"]["msg_type"]
    c = msg.get("content", {})
    if t == "stream":
        return {"output_type": "stream", "name": c.get("name", "stdout"), "text": c.get("text", "")}
    if t in ("execute_result", "display_data", "update_display_data"):
        return {
            "output_type": "execute_result" if t == "execute_result" else "display_data",
            "data": c.get("data", {}),
            "metadata": c.get("metadata", {}),
            **({"execution_count": c.get("execution_count")} if t == "execute_result" else {}),
        }
    if t == "error":
        return {
            "output_type": "error",
            "ename": c.get("ename", ""),
            "evalue": c.get("evalue", ""),
            "traceback": c.get("traceback", []),
        }
    return None


def print_output(msg: dict, limit: int = 4000) -> None:
    t = msg["header"]["msg_type"]
    c = msg.get("content", {})
    if t == "stream":
        text = c.get("text", "")
        print(f"    {'> ' if c.get('name') == 'stderr' else '  '}{text.rstrip()[:limit]}")
    elif t in ("execute_result", "display_data"):
        for mime, val in (c.get("data") or {}).items():
            if mime in ("text/plain", "text/html"):
                print(f"    [{mime}] {str(val).rstrip()[:limit]}")
    elif t == "error":
        print(f"    ERROR {c.get('ename')}: {c.get('evalue')}")
        for line in (c.get("traceback") or [])[-12:]:
            print(f"    {line.rstrip()}")


def run_cell(ws, code: str, timeout: float, verbose: bool) -> tuple[bool, list[dict], float]:
    """Execute one cell; returns (ok, nbformat_outputs, elapsed)."""
    req = jmsg("shell", "execute_request", {
        "code": code, "silent": False, "store_history": True,
        "user_expressions": {}, "allow_stdin": False, "stop_on_error": True,
    })
    ws.send(req)
    start = time.time()
    deadline = start + timeout
    outputs: list[dict] = []
    status = None
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return False, outputs, time.time() - start
        ws.settimeout(max(0.5, remaining))
        try:
            frame = ws.recv()
        except websocket.WebSocketTimeoutException:
            return False, outputs, time.time() - start
        if frame is None:
            continue
        if isinstance(frame, (bytes, bytearray)):
            if verbose:
                print(f"    [binary output, {len(frame)} bytes]")
            continue
        msg = json.loads(frame)
        t = msg["header"]["msg_type"]
        if msg.get("channel") == "shell" and t == "execute_reply":
            status = msg["content"].get("status", "error")
            if verbose and status == "error":
                print_output(msg)
            break
        out = to_nb_output(msg)
        if out is not None:
            outputs.append(out)
            if verbose:
                print_output(msg)
    return status == "ok", outputs, time.time() - start


def main() -> None:
    ap = argparse.ArgumentParser(description="Run notebook cells on the docker-compose Jupyter server")
    ap.add_argument("notebook")
    ap.add_argument("--url", default="http://localhost:8888")
    ap.add_argument("--token", default=os.environ.get("JUPYTER_TOKEN", ""))
    ap.add_argument("--python-path", default="/opt/spark/scripts")
    ap.add_argument("--cell", type=int, action="append", dest="cells", default=None,
                    help="cell index (repeatable); default all code cells")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--write", action="store_true", help="write outputs back into the .ipynb")
    ap.add_argument("--keep-kernel", action="store_true")
    args = ap.parse_args()

    nb = nbformat.read(args.notebook, as_version=4)
    code_cells = [i for i, c in enumerate(nb.cells) if c.cell_type == "code"]
    if args.cells is not None:
        targets = []
        n = len(nb.cells)
        for i in args.cells:
            j = i + n if i < 0 else i
            if not 0 <= j < n or nb.cells[j].cell_type != "code":
                sys.exit(f"error: cell {i} is not a code cell")
            targets.append(j)
    else:
        targets = code_cells
    if not targets:
        print("nothing to do: no code cells selected")
        return

    srv = Server(args.url, args.token or None)
    try:
        srv.api("GET", "/api")
    except Exception:
        sys.exit(f"error: Jupyter server not reachable at {args.url}\n"
                 f"       start it with: docker compose up -d jupyter")

    kid = srv.start_kernel()
    print(f"kernel {kid[:8]}... starting")
    try:
        # the server only requests kernel_info (and leaves the 'starting'
        # state) once a websocket client connects — connect first, then wait
        ws = websocket.create_connection(srv.ws_url(kid), timeout=15)
        srv.wait_idle(kid)
        print(f"connected: {srv.ws_url(kid)}")

        prologue = f"import sys; sys.path.insert(0, {args.python_path!r})" if args.python_path else None
        if prologue:
            ok, _, dt = run_cell(ws, prologue, 30.0, verbose=False)
            if not ok:
                sys.exit(f"error: prologue failed ({args.python_path} not settable?)")

        failed = False
        for i in targets:
            src = "".join(nb.cells[i].get("source", []))
            print(f"\ncell {i}: {src.strip().splitlines()[0][:70] if src.strip() else '<empty>'}")
            ok, outputs, dt = run_cell(ws, src, args.timeout, verbose=True)
            tag = "ok" if ok else "FAILED"
            print(f"cell {i}: {tag} ({dt:.1f}s)")
            if args.write and ok:
                nb.cells[i]["outputs"] = outputs
                nb.cells[i]["execution_count"] = (nb.cells[i].get("execution_count") or 0) + 1
            if not ok:
                failed = True
                break
        ws.close()
        if args.write and not failed:
            # nbformat write expects NotebookNode objects, not plain dicts
            nb = nbformat.from_dict(dict(nb))
            nbformat.validate(nb)
            nbformat.write(nb, args.notebook)
            print(f"\noutputs written to {args.notebook}")
    finally:
        if not args.keep_kernel:
            srv.stop_kernel(kid)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
