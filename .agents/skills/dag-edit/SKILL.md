---
name: dag-edit
description: Wire Spark scripts/notebooks into Airflow DAGs in this repo — create SparkApplication manifests under dags/**/spark-apps/, register get_spark_operator tasks, and build correct task dependencies. Use whenever asked to add a script to a DAG, create or modify a spark-apps manifest, or change task dependencies in dags/.
---

# DAG Editing (Airflow + SparkApplication)

## Environment

- Run everything from the repo root with `uv run ...` (uses the repo `.venv`,
  Python 3.14). Never use system `python3` for validation — packages like
  `pyyaml` live in the uv env, not system Python.
- `pyyaml` (parse manifests) is in `[dependency-groups].dev` in `pyproject.toml`.
  If you need another package: `uv add --dev <pkg>` (keeps `uv.lock` in sync).
- Spark images: `make build-images` builds the chain base -> spark -> jupyter
  (the operator runs jobs in `unidata-spark:4.1.2`).

## Helper script

```bash
CHK=".agents/skills/dag-edit/scripts/check_spark_app.py"

uv run python $CHK                       # validate every dags/**/spark-apps/*.yaml
uv run python $CHK dags/.../spark-apps/x.yaml [more.yaml ...]
```

Checks per manifest: valid YAML; `apiVersion`/`kind` are the spark operator's;
`metadata.name` matches the file name (dashes); `spec.mainApplicationFile`
starts with `local:///opt/spark/scripts/` and its basename is the app name with
`-` → `_` plus `.py`; the CI source script (`.ipynb` or `.py`) exists under
`scripts/` in the repo; required spec keys present (`type`, `mode`, `image`,
`mainApplicationFile`, `sparkVersion`, `driver`, `executor`). Exit 1 on any
failure.

## Add a script to a DAG

When asked `add <script> to <dag>` (e.g. `add scripts/gold/proplan/turmas/cria_tbl_matriculas_turma.ipynb to dags/gold/evasao/cria_indicadores_proplan.py`), follow these steps:

1. **Read both files** to understand the DAG structure and the script (Spark session name, source/target tables).

2. **Create the SparkApplication manifest** at `<dag_dir>/spark-apps/<app-name>.yaml` (the DAG folder, e.g. `dags/gold/evasao/spark-apps/`), modeled on an existing manifest in that folder. Conventions:
   - `<app-name>` is the script file name with `_` → `-` (e.g. `cria_tbl_matriculas_turma.ipynb` → `cria-tbl-matriculas-turma`).
   - `mainApplicationFile` points to the **CI-generated** `.py` file: `local:///opt/spark/scripts/<subdir>/<script_name>.py`. The airflow entrypoint (`docker/airflow/entrypoint.sh`) nbconverts every `.ipynb` under `scripts/` to `.py` in place on startup; do **not** create the `.py` by hand.
   - Keep the same image, sparkConf, driver/executor, and env blocks as the sibling manifests.

3. **Align the notebook session name**: the first cell's `cria_spark_session("<name>")` must match the app name (dashes). Fix a mismatched/copied session name (e.g. a session name inherited from another script). For notebook edits, use the `nb-edit` skill.

4. **Register the task in the DAG**: add a `get_spark_operator` task with `task_id="cria_<name>"`, `application_file="spark-apps/<app-name>.yaml"`, and insert it into the existing dependency chain (after the namespace setup task, before the `_ready` outlet task) alongside sibling table tasks. In this demo the operator runs the script locally: a `BashOperator` that launches the script inside the `unidata-spark:4.1.2` image via `dags/utils/dev_spark_run.sh` (docker socket) — no k8s args (`kubernetes_conn_id` etc. are dropped).

5. **Validate**: confirm the DAG file parses (`uv run python -c "import ast; ast.parse(open('<dag>').read())"`), run the manifest checker (`uv run python $CHK <new-manifest>`), and, for notebook edits, that the JSON still loads (see the `nb-edit` skill).

## Task dependencies in DAGs

- A `>>` chain of lists (e.g. `[a_task, b_task] >> [c_task, d_task]`) means every task in the first list runs **in parallel**, and the second list starts only after all of them finish. Never build orderings that rely on lists being sequential.
- Never place a sequence inside a list: `[a_task, b_task >> c_task, d_task]` is invalid style here — everything in a single list runs in parallel.
- To run an ordered stage after a group of parallel tasks, glue the two together with an auxiliary `PythonOperator` marker task (e.g. `inicia_segunda_etapa`), as in:

```python
        >> [
            task_parallel_1,
            task_parallel_2,
        ]
        >> inicia_etapa_x_task  # PythonOperator marker
        >> etapa_sequencial_task
```
