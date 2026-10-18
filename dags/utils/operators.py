"""Factory de operador Spark para execucao local (demo).

Retorna um `BashOperator` que executa o script do manifesto SparkApplication
dentro da imagem Spark (`unidata-spark:4.1.2`) via o launcher
`dags/utils/dev_spark_run.sh` (usa o docker socket montado no container do
airflow).

O script executado e o `spec.mainApplicationFile` do manifesto (.yaml)
convertido para o caminho dentro do container
(ex.: `local:///opt/spark/scripts/00_bronze/foo.py` -> `/opt/spark/scripts/00_bronze/foo.py`).
O container do job entra na rede do compose (env `SPARK_JOB_NETWORK`) para
resolver nessie/minio/postgres por nome de servico.
"""

import logging
import os
import shlex
from pathlib import Path

import yaml
from airflow.providers.standard.operators.bash import BashOperator

log = logging.getLogger(__name__)

_DAGS_ROOT = Path(__file__).resolve().parents[1]  # dags/
_REPO_ROOT = Path(__file__).resolve().parents[2]  # repo (quando montado junto)
# Launcher co-localizado; lido em runtime pelo BashOperator.
_DEV_SPARK_SCRIPT = Path(__file__).resolve().parent / "dev_spark_run.sh"


def _resolve_manifest(application_file: str) -> Path:
    """Resolve o manifesto SparkApplication.

    Caminho relativo e resolvido primeiro em relacao ao diretorio do proprio
    arquivo da DAG (convencao de todas as DAGs: ``spark-apps/<name>.yaml`` ao
    lado da DAG). Se nao achar, cai para busca por basename — que ERRA em vez
    de sortear a primeira em ordem alfabetica quando o basename e ambiguo
    (ex.: dois DAGs com manifesto ``cria-tbl-conclusao.yaml``).
    """
    p = Path(application_file)
    if p.exists():
        return p
    dag = _current_dag()
    if dag is not None and getattr(dag, "fileloc", None):
        candidate = Path(dag.fileloc).parent / p
        if candidate.exists():
            return candidate
    name = p.name
    for base in (_DAGS_ROOT, _REPO_ROOT / "dags", _REPO_ROOT):
        matches = sorted(base.rglob(name)) if base.exists() else []
        if len(matches) > 1:
            raise FileNotFoundError(
                f"Manifesto SparkApplication ambíguo {name!r}: "
                f"{[str(m) for m in matches]} — use caminho relativo à pasta da DAG."
            )
        if matches:
            return matches[0]
    raise FileNotFoundError(
        f"SparkApplication manifest not found: {application_file} (basename: {name})"
    )


def _current_dag():
    """DAG em parsing (None se chamado fora de um bloco ``with DAG(...)``)."""
    try:
        from airflow.sdk.definitions._internal.contextmanager import DagContext
    except ImportError:  # Airflow < 3
        try:
            from airflow.models.dag import get_current_dag
        except ImportError:
            return None
        return get_current_dag()
    return DagContext.get_current_dag()


def to_repo_script_path(main_application_file: str) -> str:
    """`local:///opt/spark/scripts/x.py` -> `scripts/x.py` (relativo ao repo).

    No container do job o repo e montado em `/opt/spark/work-dir` e a pasta de
    scripts em `/opt/spark/scripts`, por isso o manifesto usa prefixo
    `/opt/spark/` que precisa ser removido para virar caminho de repo.
    """
    path = main_application_file
    for prefix in ("local://", "file://", "hdfs://", "s3://"):
        if path.startswith(prefix):
            path = path[len(prefix) :]
            break
    for prefix in ("/opt/spark/",):
        if path.startswith(prefix):
            path = path[len(prefix) :]
            break
    return path.lstrip("/")


def get_spark_operator(task_id: str, application_file: str, **kwargs):
    """Operador local: BashOperator que dispara o launcher `dev_spark_run.sh`."""
    manifest_path = _resolve_manifest(application_file)
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    repo_root = os.environ.get("UNIDATA_REPO_DIR", ".")
    script_rel = to_repo_script_path(manifest["spec"]["mainApplicationFile"])
    script_abs = "/".join(filter(None, [repo_root.rstrip("/"), script_rel]))
    if not Path(script_abs).exists():
        raise FileNotFoundError(
            f"script nao encontrado para {task_id}: {script_abs} "
            f"(original: {manifest['spec']['mainApplicationFile']})"
        )
    if not _DEV_SPARK_SCRIPT.exists():
        raise FileNotFoundError(
            f"launcher nao encontrado: {_DEV_SPARK_SCRIPT} (para {task_id})"
        )
    # O launcher (.sh) lê REPO_ROOT/TASK_ID/SCRIPT_REL do ambiente; passamos
    # cada um como atribuicao de variavel (cifrada) para o `bash` unico.
    #
    # NOTE: o comando NÃO pode terminar em `.sh` — o templater do
    # Airflow 3 (BashOperator.template_ext) trata qualquer `bash_command`
    # terminando em .sh/.bash como ARQUIVO a carregar do template search
    # path, causando TemplateNotFound. O comentário final evita isso.
    command = (
        f"REPO_ROOT={shlex.quote(repo_root)} "
        f"TASK_ID={shlex.quote(task_id)} "
        f"SCRIPT_REL={shlex.quote(script_rel)} "
        f"bash {shlex.quote(str(_DEV_SPARK_SCRIPT))} # local: spark-submit na imagem Spark"
    )
    k8s_only = {
        "namespace",
        "kubernetes_conn_id",
        "spark_conf_overrides",
        "on_failure_delete_spark_app",
        "delete_spark_app_on_failure",
        "conf",
    }
    dropped = [k for k in list(kwargs) if k in k8s_only]
    for k in dropped:
        del kwargs[k]
    if dropped:
        log.info("local mode: ignorando args k8s-only em %s: %s", task_id, dropped)
    return BashOperator(task_id=task_id, bash_command=command, **kwargs)
