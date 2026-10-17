"""Aplica o ETL sakila no data lake.

Extrai as 15 tabelas do sakila para o catalogo Nessie/Iceberg
(schema ``bronze_sakila``) e carrega todos os CSVs do bucket ``raw``
(MinIO) para o schema ``bronze_raw``. Em seguida monta a camada silver
a partir do bronze sakila: ``dim_customer``, ``dim_staff``,
``fact_payment`` e ``fact_rental`` (schema ``silver``) e fecha com o KPI
gold ``top3_customer_quarter`` (schema ``gold``): top 3 clientes por ano e
trimestre. As escritas sao idempotentes (``createOrReplace``), entao cada
execucao recria as tabelas sem duplicar.
"""

from datetime import UTC, datetime

from airflow import DAG
from utils.operators import get_spark_operator

with DAG(
    dag_id="aplica_elt_sakila",
    description="Aplica o ETL sakila: bronze (Postgres + raw CSV), silver (dim/fact) e gold (KPI top3) no Nessie/Iceberg",
    start_date=datetime(2026, 10, 14, tzinfo=UTC),
    catchup=False,
    tags=["bronze", "silver", "gold", "sakila", "raw"],
) as dag:
    # Etapa 1 — bronze: extracao do sakila (Postgres) e dos CSVs do bucket
    # 'raw'. Independentes entre si: rodam em paralelo.
    extrai_sakila_bronze = get_spark_operator(
        task_id="extrai_sakila_bronze",
        application_file="spark-apps/extrai-sakila-bronze.yaml",
    )

    ingest_raw = get_spark_operator(
        task_id="ingest_raw",
        application_file="spark-apps/ingest-raw.yaml",
    )

    # Etapa 2 — silver: cria o namespace e, depois, as tabelas dim/fact
    # em paralelo.
    cria_namespace_silver = get_spark_operator(
        task_id="cria_namespace_silver",
        application_file="spark-apps/cria-namespace-silver.yaml",
    )

    cria_dim_customer_silver = get_spark_operator(
        task_id="cria_dim_customer_silver",
        application_file="spark-apps/cria-dim-customer-silver.yaml",
    )

    cria_dim_staff_silver = get_spark_operator(
        task_id="cria_dim_staff_silver",
        application_file="spark-apps/cria-dim-staff-silver.yaml",
    )

    cria_fact_payment_silver = get_spark_operator(
        task_id="cria_fact_payment_silver",
        application_file="spark-apps/cria-fact-payment-silver.yaml",
    )

    cria_fact_rental_silver = get_spark_operator(
        task_id="cria_fact_rental_silver",
        application_file="spark-apps/cria-fact-rental-silver.yaml",
    )

    # Etapa 3 — gold: KPI a partir do silver. O namespace nao depende de
    # nenhuma tarefa e roda em paralelo desde o inicio.
    cria_namespace_gold = get_spark_operator(
        task_id="cria_namespace_gold",
        application_file="spark-apps/cria-namespace-gold.yaml",
    )

    cria_top3_customer_quarter_gold = get_spark_operator(
        task_id="cria_top3_customer_quarter_gold",
        application_file="spark-apps/cria-top3-customer-quarter-gold.yaml",
    )

    # O silver depende da extracao do sakila (fonte dos dados) e do
    # namespace ja criado.
    extrai_sakila_bronze >> cria_namespace_silver >> [
        cria_dim_customer_silver,
        cria_dim_staff_silver,
        cria_fact_payment_silver,
        cria_fact_rental_silver,
    ]

    # O KPI gold depende do namespace gold e das tabelas de origem
    # (fact_payment + dim_customer).
    [
        cria_fact_payment_silver,
        cria_dim_customer_silver,
        cria_namespace_gold,
    ] >> cria_top3_customer_quarter_gold
