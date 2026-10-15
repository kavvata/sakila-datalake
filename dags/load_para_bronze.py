"""Carga da fonte sakila (Postgres) e dos arquivos raw (CSV) para a camada
bronze do data lake.

Extrai as 15 tabelas do sakila para o catalogo Nessie/Iceberg
(schema ``bronze_sakila``) e carrega todos os CSVs do bucket ``raw``
(MinIO) para o schema ``bronze_raw``. As escritas sao idempotentes
(``createOrReplace``), entao cada execucao recria as tabelas sem duplicar.
"""

from datetime import datetime, timezone

from airflow import DAG
from utils.operators import get_spark_operator

with DAG(
    dag_id="load_para_bronze",
    description="Extrai as tabelas sakila (Postgres) para a camada bronze (Nessie/Iceberg)",
    start_date=datetime(2026, 10, 14, tzinfo=timezone.utc),
    catchup=False,
    tags=["bronze", "sakila", "raw"],
) as dag:
    extrai_sakila_bronze = get_spark_operator(
        task_id="extrai_sakila_bronze",
        application_file="spark-apps/extrai-sakila-bronze.yaml",
    )

    # independente do sakila: roda em paralelo (todos os CSVs do bucket 'raw')
    ingest_raw = get_spark_operator(
        task_id="ingest_raw",
        application_file="spark-apps/ingest-raw.yaml",
    )
