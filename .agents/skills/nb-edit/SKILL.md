---
name: nb-edit
description: Edit Jupyter .ipynb notebooks in this repo safely (valid nbformat JSON, clean diffs, CI-compatible output) using the uv-managed environment, and execute notebook cells on the compose Jupyter server for runtime validation. Use whenever creating, modifying, validating, converting, or running any .ipynb file, especially under scripts/.
---

# Notebook Editing (.ipynb)

Never hand-write raw notebook JSON. Edit `.ipynb` files through `nbformat` in the
project's uv environment — it guarantees the file stays valid nbformat-4 and
preserves cell ids, metadata, and outputs.

## Environment

- Run everything from the repo root with `uv run ...` (uses the repo `.venv`, Python 3.10).
- Dev packages for this workflow (already in `[dependency-groups].dev` in `pyproject.toml`):
  `nbformat` (read/validate/write), `nbclient` (execute), `nbconvert` (convert/execute),
  `websocket-client` (talk to the Jupyter server kernel channel). `ipykernel` is in the
  main dependencies.
- If you need an extra package: `uv add --dev <pkg>` (keeps `uv.lock` in sync).

## Helper script

```bash
NB=".agents/skills/nb-edit/scripts/nb_edit.py"

uv run python $NB show      <nb.ipynb>                     # list cells (idx, type, first line)
uv run python $NB cell      <nb.ipynb> <idx>               # print full source of a cell
uv run python $NB set       <nb.ipynb> <idx> <file|->      # replace a cell's source
uv run python $NB insert    <nb.ipynb> <file|-> [--after i] [--type code|markdown]
uv run python $NB delete    <nb.ipynb> <idx>
uv run python $NB clear-outputs <nb.ipynb>                 # blank outputs + execution counts
uv run python $NB set-session <nb.ipynb> <app-name>        # fix cria_spark_session app name
uv run python $NB validate  <nb.ipynb> [more.ipynb ...]    # validate without modifying
```

- Cell indices support negatives (`-1` = last cell). `insert` without `--after` appends.
- **Every write command re-validates the notebook before saving** and refuses to
  write an invalid file.

## Workflow

1. **Inspect** the cells you will touch: `show`, then `cell <idx>`.
2. **Edit** via the helper subcommands. If a tiny change really requires editing the
   raw JSON with your text editor, treat the file as strict JSON (no trailing commas,
   strings must be escaped), then run `validate` immediately after.
3. **Validate**: `uv run python $NB validate <nb.ipynb>` on every notebook you touched.
   Also check `git diff -- <nb.ipynb>` — a correct edit shows only the source lines
   you changed, not a whole-file reformat (nbformat's round-trip is stable).
   Caveat: notebooks saved by older Jupyter versions may have non-canonical key
   order inside cells; the first save normalizes the order (content-identical,
   one-time mechanical diff) and is safe to commit.
4. **CI conversion check** (mandatory for notebooks under `scripts/`): CI nbconverts
   every notebook in place and the generated `.py` is what Spark executes. Verify the
   conversion still produces valid Python without polluting the repo:
   ```bash
   uv run jupyter nbconvert --to python --stdout scripts/.../<nb>.ipynb > /tmp/<nb>_check.py
   uv run python -m py_compile /tmp/<nb>_check.py
   ```
   Do **not** create the `.py` by hand and do not leave generated `.py` files behind
   (they are gitignored under `scripts/{bronze,silver,gold}/**`).
5. **Runtime check on the compose Jupyter server** (recommended whenever a cell's
   logic changed and the notebook is meant to run): execute the cells in the Jupyter
   container from `docker-compose.yml` (same Spark env, repo mounted at `/workspace`,
   env vars from `.env`). Start it if it is not up:
   ```bash
   docker compose up -d jupyter        # or: make up-nb
   ```
   then, from the repo root:
   ```bash
   RUN=".agents/skills/nb-edit/scripts/nb_run.py"
   uv run python $RUN scripts/.../<nb>.ipynb                 # run all code cells
   uv run python $RUN scripts/.../<nb>.ipynb --cell 17       # only cell 17 (0-based)
   uv run python $RUN scripts/.../<nb>.ipynb --cell 0 --cell 1 --write   # also save outputs
   ```
   - A fresh `python3` kernel is started per run and shut down afterwards
     (`--keep-kernel` to reuse); per-cell timeout defaults to 300s (`--timeout`).
   - The runner prepends `/workspace/scripts` to `sys.path` in the kernel
     (`--python-path`, pass `""` to disable) so `from nucleo import ...` resolves.
   - Prints per-cell stdout/stderr/results; on failure it prints the traceback and
     exits 1.
   - **Cells really execute**: DDL/ingest against the dev Nessie/Minio targets from
     `.env`. Prefer idempotent notebooks (e.g. `CREATE ... IF NOT EXISTS`) or
     `--cell` selection; do not blindly re-run full ETL notebooks.

## Project conventions

- The first code cell creates the Spark session: `cria_spark_session("<app-name>")`,
  either directly or via `SPARK_APP_NAME = "<app-name>"`. The name must match the
  SparkApplication manifest name (dashes, e.g. `cria-tbl-matriculas-turma`).
  Fix a mismatch with: `uv run python $NB set-session <nb.ipynb> <app-name>`.
- Keep notebook edits minimal and stay consistent with sibling notebooks in the
  same folder (imports, session pattern, output style).
- When the user asks to **show me** something (schema, sample rows, results, ...),
  they want to see it in their editor: run `nb_run` with the `--write` flag so the
  outputs are persisted into the `.ipynb` (e.g.
  `uv run python $RUN <nb.ipynb> --cell 2 --cell 3 --write`). Only run the cells
  whose outputs matter (the new `printSchema`/`show` cells), never the whole
  notebook, unless the user asked for a full run.
