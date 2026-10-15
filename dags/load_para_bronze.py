"""Carga da fonte sakila (Postgres) para a camada bronze do data lake.

Extrai as 15 tabelas do sakila para o catalogo Nessie/Iceberg
(schema ``bronze_sakila``). A escrita e idempotente (``createOrReplace``),
entao cada execucao reextrai o dado completo sem duplicar.
"""

from datetime import datetime

from airflow import DAG

from utils.operators import get_spark_operator

with DAG(
    dag_id="load_para_bronze",
    description="Extrai as tabelas sakila (Postgres) para a camada bronze (Nessie/Iceberg)",
    start_date=datetime(2026, 10, 14),
    catchup=False,
    tags=["bronze", "sakila"],
) as dag:
    extrai_sakila_bronze = get_spark_operator(
        task_id="extrai_sakila_bronze",
        application_file="spark-apps/extrai-sakila-bronze.yaml",
    )
