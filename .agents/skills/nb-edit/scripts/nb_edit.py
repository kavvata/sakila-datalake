#!/usr/bin/env python3
"""Safe Jupyter notebook (.ipynb) editor built on nbformat.

Every write command validates the notebook before saving, so an invalid
file is never written to disk. Run from the repo root with:

    uv run python .agents/skills/nb-edit/scripts/nb_edit.py <command> ...

Commands:
    show           list cells (index, type, first line)
    cell           print one cell's full source
    set            replace a cell's source (from file or stdin via -)
    insert         insert a new code/markdown cell after a given index
    delete         delete a cell
    clear-outputs  remove outputs and execution counts (all code cells)
    set-session    fix the cria_spark_session("<name>") app name
    validate       validate one or more notebooks without modifying them
"""
from __future__ import annotations

import argparse
import re
import sys

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell


def load(path: str) -> nbformat.NotebookNode:
    try:
        return nbformat.read(path, as_version=4)
    except Exception as exc:
        sys.exit(f"error: cannot read {path}: {exc}")


def save(nb: nbformat.NotebookNode, path: str) -> None:
    try:
        nbformat.validate(nb)
    except nbformat.ValidationError as exc:
        sys.exit(f"error: refusing to write invalid notebook {path}:\n{exc}")
    nbformat.write(nb, path)
    print(f"ok: {path} (valid, {len(nb.cells)} cells)")


def cell_src(cell) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def set_src(cell, src: str) -> None:
    """Store source as list of lines, '\n' on every line except the last
    (the same layout Jupyter/nbformat use, keeps diffs clean)."""
    lines = src.splitlines()
    cell["source"] = [line + "\n" for line in lines[:-1]] + (
        [lines[-1]] if lines else []
    )


def read_source(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    with open(arg, encoding="utf-8") as fh:
        return fh.read()


def idx(nb: nbformat.NotebookNode, i: int) -> int:
    n = len(nb.cells)
    if i < 0:
        i += n
    if not 0 <= i < n:
        sys.exit(f"error: cell index {i} out of range (notebook has {n} cells)")
    return i


def cmd_show(nb: nbformat.NotebookNode, _args) -> None:
    for i, cell in enumerate(nb.cells):
        first = next((l for l in cell_src(cell).splitlines() if l.strip()), "")
        extra = ""
        if cell.cell_type == "code" and cell.get("execution_count") is not None:
            extra = f" [exec {cell['execution_count']}]"
        print(f"{i:>3} {cell.cell_type:<8} {first[:70]}{extra}")


def cmd_cell(nb: nbformat.NotebookNode, args) -> None:
    i = idx(nb, args.index)
    sys.stdout.write(cell_src(nb.cells[i]))


def cmd_set(nb: nbformat.NotebookNode, args) -> None:
    i = idx(nb, args.index)
    set_src(nb.cells[i], read_source(args.source))
    save(nb, args.notebook)


def cmd_insert(nb: nbformat.NotebookNode, args) -> None:
    if args.after is None:
        pos = len(nb.cells)
    else:
        pos = idx(nb, args.after) + 1
    source = read_source(args.source) if args.source else ""
    cell = new_markdown_cell(source) if args.type == "markdown" else new_code_cell(source)
    nb.cells.insert(pos, cell)
    save(nb, args.notebook)


def cmd_delete(nb: nbformat.NotebookNode, args) -> None:
    i = idx(nb, args.index)
    del nb.cells[i]
    save(nb, args.notebook)


def cmd_clear_outputs(nb: nbformat.NotebookNode, args) -> None:
    for cell in nb.cells:
        if cell.cell_type == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    save(nb, args.notebook)


def cmd_set_session(nb: nbformat.NotebookNode, args) -> None:
    """Rewrite the app name passed to cria_spark_session in the first
    matching code cell. Handles both patterns used in this repo:

        spark = cria_spark_session("app-name")
        SPARK_APP_NAME = "app-name"
        spark = cria_spark_session(SPARK_APP_NAME)
    """
    literal = re.compile(r"cria_spark_session\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        src = cell_src(cell)
        m = literal.search(src)
        if m:
            set_src(
                cell,
                re.sub(
                    literal,
                    lambda mm: mm.group(0).replace(mm.group(1), args.name),
                    src,
                    count=1,
                ),
            )
            save(nb, args.notebook)
            return
    var = re.compile(r"(SPARK_APP_NAME\s*=\s*['\"])([^'\"]+)(['\"])")
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        src = cell_src(cell)
        if var.search(src):
            set_src(
                cell,
                re.sub(
                    var,
                    lambda mm: f"{mm.group(1)}{args.name}{mm.group(3)}",
                    src,
                    count=1,
                ),
            )
            save(nb, args.notebook)
            return
    sys.exit("error: no cria_spark_session('...') or SPARK_APP_NAME = '...' found in code cells")


def cmd_validate(_nb: nbformat.NotebookNode, args) -> None:
    for path in args.notebooks:
        nb = load(path)
        try:
            nbformat.validate(nb)
            print(f"ok: {path} (nbformat {nb['nbformat']}.{nb['nbformat_minor']}, {len(nb.cells)} cells)")
        except nbformat.ValidationError as exc:
            print(f"INVALID: {path}:\n{exc}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def make(name, fn):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        return p

    p = make("show", cmd_show)
    p.add_argument("notebook")

    p = make("cell", cmd_cell)
    p.add_argument("notebook")
    p.add_argument("index", type=int)

    p = make("set", cmd_set)
    p.add_argument("notebook")
    p.add_argument("index", type=int)
    p.add_argument("source", help="new cell source (file, or - for stdin)")

    p = make("insert", cmd_insert)
    p.add_argument("notebook")
    p.add_argument("source", nargs="?", default=None, help="cell source (file, or - for stdin)")
    p.add_argument("--after", type=int, default=None, help="insert after this cell index (default: append)")
    p.add_argument("--type", choices=["code", "markdown"], default="code")

    p = make("delete", cmd_delete)
    p.add_argument("notebook")
    p.add_argument("index", type=int)

    p = make("clear-outputs", cmd_clear_outputs)
    p.add_argument("notebook")

    p = make("set-session", cmd_set_session)
    p.add_argument("notebook")
    p.add_argument("name")

    p = make("validate", cmd_validate)
    p.add_argument("notebooks", nargs="+")

    args = parser.parse_args()

    if args.command == "validate":
        args.fn(None, args)
        return

    nb = load(args.notebook)
    args.fn(nb, args)


if __name__ == "__main__":
    main()
