---
name: nb-edit
description: Edit Jupyter .ipynb notebooks in this repo safely by round-tripping them through markdown (valid nbformat JSON, clean diffs, CI-compatible output) using the uv-managed environment, and execute notebook cells on the compose Jupyter server for runtime validation. Use whenever creating, modifying, validating, converting, or running any .ipynb file, especially under scripts/.
---

# Notebook Editing (.ipynb)

Never hand-write or hand-edit raw notebook JSON. Edit `.ipynb` files by
round-tripping them through markdown with the `convert` command: export the
notebook to a `.md`, edit the plain text, convert back. The helper guarantees
the file stays valid nbformat-4.

## Environment

- Run everything from the repo root with `uv run ...` (uses the repo `.venv`, Python 3.14).
- Dev packages for this workflow (already in `[dependency-groups].dev` in `pyproject.toml`):
  `nbformat` (read/validate/write), `nbclient` (execute), `nbconvert` (convert/execute),
  `websocket-client` (talk to the Jupyter server kernel channel). `ipykernel` is in the
  Jupyter image (the notebook kernel inside the container), not in the repo deps.
- If you need an extra package: `uv add --dev <pkg>` (keeps `uv.lock` in sync).

## Helper script

```bash
NB=".agents/skills/nb-edit/scripts/nb_edit.py"

uv run python $NB convert  <in.md|in.ipynb> <out.ipynb|out.md>  # direction by input extension
uv run python $NB validate <nb.ipynb> [more.ipynb ...]          # validate without modifying
```

- `convert` with a `.md` input builds a notebook: ` ```python ` fenced blocks
  become code cells, all other text becomes markdown cells, blank-only blocks
  are dropped. `convert` with a `.ipynb` input exports cells to markdown
  (markdown cells as-is, code cells wrapped in ` ```python ` fences).
- **Every write re-validates the notebook before saving** and refuses to
  write an invalid file.

## Markdown conventions (the converter enforces these)

- Only fences that read exactly ` ```python ` become code cells. Any other
  language (` ```py `, ` ```sql `, ...) silently stays markdown text — never
  use it for code you want executed.
- A line that is exactly ` ``` ` closes a code block, so code must not contain
  bare ` ``` ` lines.
- An unclosed ` ```python ` fence is a hard error: nothing is written.

## Workflow

1. **Export** the notebook to a temporary markdown file:
   ```bash
   uv run python $NB convert scripts/.../<nb>.ipynb /tmp/<nb>.md
   ```
2. **Edit** the `.md` like any text file. Markdown between code blocks becomes
   markdown cells; keep the ` ```python ` blocks as the code.
3. **Convert back** over the original path:
   ```bash
   uv run python $NB convert /tmp/<nb>.md scripts/.../<nb>.ipynb
   ```
   It prints the cell list it built. The round trip regenerates cell ids,
   drops cell outputs, and normalizes metadata to
   `{"language_info": {"name": "python"}}` — content is otherwise preserved.
4. **Validate**: `uv run python $NB validate <nb.ipynb>` on every notebook you
   touched (convert already re-validates before saving). Also check
   `git diff -- <nb.ipynb>` — a correct edit shows only the cells you changed,
   plus the regenerated cell ids.
5. **Conversion check** (mandatory for notebooks under `scripts/`): the airflow
   entrypoint (`docker/airflow/entrypoint.sh`) nbconverts every notebook in
   place on startup and the generated `.py` is what Spark executes. Verify the
   conversion still produces valid Python without polluting the repo:
   ```bash
   uv run python -m nbconvert --to python --stdout scripts/.../<nb>.ipynb > /tmp/<nb>_check.py
   uv run python -m py_compile /tmp/<nb>_check.py
   ```
   Markdown cells become `#` comments in the generated `.py`, so text cells are
   execution-safe. Do not create the `.py` by hand and do not leave generated
   `.py` files behind (they are gitignored under `scripts/{bronze,silver,gold}/**`).
6. **Runtime check on the compose Jupyter server** (recommended whenever a
   code cell's logic changed and the notebook is meant to run): execute the
   cells in the Jupyter container from `docker-compose.yml` (same Spark env,
   repo mounted at `/opt/spark/work-dir`, env vars from `.env`). Start it if it
   is not up:
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
   - The runner prepends `/opt/spark/scripts` to `sys.path` in the kernel
     (`--python-path`, pass `""` to disable) so `from nucleo import ...` resolves.
   - Prints per-cell stdout/stderr/results; on failure it prints the traceback and
     exits 1.
   - **Cells really execute**: DDL/ingest against the dev Nessie/Minio targets from
     `.env`. Prefer idempotent notebooks (e.g. `CREATE ... IF NOT EXISTS`) or
     `--cell` selection; do not blindly re-run full ETL notebooks.

**Creating a new notebook**: skip step 1 — write the `.md` first (same
conventions, first code block is the session cell), convert it to the final
`.ipynb` path, then do steps 4–6.

## Project conventions

- The first code cell creates the Spark session: `cria_spark_session("<app-name>")`,
  either directly or via `SPARK_APP_NAME = "<app-name>"`. The name must match the
  SparkApplication manifest name (dashes, e.g. `cria-tbl-matriculas-turma`).
  When editing, the name is just a string in the first ` ```python ` block of
  the markdown — keep it matching.
- Keep notebook edits minimal and stay consistent with sibling notebooks in the
  same folder (imports, session pattern, output style).
- When the user asks to **show me** something (schema, sample rows, results, ...),
  they want to see it in their editor: run `nb_run` with the `--write` flag so the
  outputs are persisted into the `.ipynb` (e.g.
  `uv run python $RUN <nb.ipynb> --cell 2 --cell 3 --write`). Only run the cells
  whose outputs matter (the new `printSchema`/`show` cells), never the whole
  notebook, unless the user asked for a full run. Note: the next convert round
  trip drops outputs again — re-run with `--write` if they are needed after an
  edit.
