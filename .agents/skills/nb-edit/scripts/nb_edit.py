#!/usr/bin/env python3
"""Safe Jupyter notebook (.ipynb) editor built on nbformat.

Notebooks are edited by round-tripping them through markdown:

    uv run python .agents/skills/nb-edit/scripts/nb_edit.py convert <nb.ipynb> <nb.md>
    edit <nb.md>
    uv run python .agents/skills/nb-edit/scripts/nb_edit.py convert <nb.md> <nb.ipynb>

```python fenced blocks become code cells, all other text becomes markdown
cells. Every write validates the notebook before saving, so an invalid file
is never written to disk. Run from the repo root.

Commands:
    convert        convert between .md and .ipynb, direction by input extension
    validate       validate one or more notebooks without modifying them
"""
from __future__ import annotations

import argparse
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


def parse_md(src: str) -> list[tuple[str, str]]:
    """Split markdown into (cell_type, text) blocks: ```python fenced blocks
    become code cells, all other text becomes markdown cells (blank-only
    markdown blocks are dropped). Exits on an unclosed fence."""
    blocks: list[tuple[str, str]] = []
    md_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False
    for line in src.splitlines():
        stripped = line.strip()
        if in_code:
            if stripped == "```":
                blocks.append(("code", "".join(code_lines)))
                in_code = False
            else:
                code_lines.append(line + "\n")
        elif stripped.removeprefix("```") == "python":
            blocks.append(("markdown", "".join(md_lines)))
            md_lines, code_lines = [], []
            in_code = True
        else:
            md_lines.append(line + "\n")
    if in_code:
        sys.exit("error: unclosed ```python fence; refusing to write notebook")
    blocks.append(("markdown", "".join(md_lines)))
    return [(kind, text.strip("\n")) for kind, text in blocks if text.strip("\n")]


def nb_to_md(nb: nbformat.NotebookNode) -> str:
    """Export cells as markdown: markdown cells as-is, code cells wrapped in
    ```python fences (inverse of parse_md)."""
    parts = []
    for cell in nb.cells:
        src = cell_src(cell).strip("\n")
        if cell.cell_type == "code":
            parts.append(f"```python\n{src}\n```\n")
        else:
            parts.append(src + "\n")
    return "\n".join(parts)


def cmd_convert(nb: nbformat.NotebookNode | None, args) -> None:
    if args.source.endswith(".ipynb"):
        with open(args.target, "w", encoding="utf-8") as fh:
            fh.write(nb_to_md(nb))
        print(f"ok: {args.target} ({len(nb.cells)} cells -> markdown)")
        return
    nb = nbformat.v4.new_notebook()
    nb["metadata"] = {"language_info": {"name": "python"}}  # repo convention
    for kind, text in parse_md(read_source(args.source)):
        cell = new_code_cell() if kind == "code" else new_markdown_cell()
        set_src(cell, text)
        nb.cells.append(cell)
    save(nb, args.target)
    for i, cell in enumerate(nb.cells):
        first = next((l for l in cell_src(cell).splitlines() if l.strip()), "")
        print(f"{i:>3} {cell.cell_type:<8} {first[:70]}")


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

    p = make("convert", cmd_convert)
    p.add_argument("source", help="input .md (or - for stdin) or .ipynb")
    p.add_argument("target", help="output .ipynb (from .md) or .md (from .ipynb)")

    p = make("validate", cmd_validate)
    p.add_argument("notebooks", nargs="+")

    args = parser.parse_args()

    if args.command == "validate":
        args.fn(None, args)
        return
    nb = load(args.source) if args.source.endswith(".ipynb") else None
    args.fn(nb, args)


if __name__ == "__main__":
    main()
