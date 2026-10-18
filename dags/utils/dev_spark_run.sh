#!/usr/bin/env bash
# Launcher local para manifests SparkApplication (usado pelo BashOperator em
# dags/utils/operators.py).
#
# Roda o main script do manifesto dentro da imagem Spark copiando o CONTEUDO
# de scripts/ para um volume nomeado (evita bind mount, cujo caminho seria
# relativo ao host), e chama spark-submit contra MinIO/Nessie.
#
# Required environment:
#   TASK_ID     Airflow task id (names the scratch docker volume)
#   SCRIPT_REL  main script path relative to the repo, e.g. scripts/bronze/foo.py
#   REPO_ROOT   repo root to run from (default: ".")
#
# Optional environment (defaults below): SPARK_IMAGE SPARK_MASTER
#   SPARK_JOB_NETWORK rede docker do job (default "default"); no compose e a
#   rede default do projeto, entao o job resolve nessie/minio/postgres por
#   nome de servico.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-.}"
TASK_ID="${TASK_ID:?TASK_ID environment variable is required}"
SCRIPT_REL="${SCRIPT_REL:?SCRIPT_REL environment variable is required}"

cd "$REPO_ROOT"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

SPARK_IMAGE="${SPARK_IMAGE:-unidata-spark:4.1.2}"
SPARK_MASTER="${SPARK_MASTER:-local[*]}"
SPARK_JOB_NETWORK="${SPARK_JOB_NETWORK:-default}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-unidata}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-supersenha}"
NESSIE_URI="${NESSIE_URI:-http://nessie:19120/api/v1}"
NESSIE_REF="${NESSIE_REF:-dev}"
VOL="unidata_spark_${TASK_ID}"
SCRIPT_EXEC_REL="${SCRIPT_REL#scripts/}"

# Copia o CONTEUDO de scripts/ (nucleo/, bronze/, ...) para o volume nomeado,
# montado em /opt/spark/scripts; evita bind mount (caminho seria do host).
docker volume rm "$VOL" >/dev/null 2>&1 || true
docker volume create "$VOL" >/dev/null
tar -C scripts -czf - . |
  docker run -i --rm -u 0 -v "$VOL:/staging" --entrypoint /usr/bin/tar "$SPARK_IMAGE" -C /staging -xz

docker run --rm \
  --network "$SPARK_JOB_NETWORK" \
  -v "$VOL:/opt/spark/scripts" \
  -e MINIO_ENDPOINT="$MINIO_ENDPOINT" \
  -e MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
  -e MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
  -e NESSIE_URI="$NESSIE_URI" \
  -e NESSIE_REF="$NESSIE_REF" \
  -e POSTGRES_URL="${POSTGRES_URL:-jdbc:postgresql://postgres:5432/${POSTGRES_DB:-sakila}}" \
  -e POSTGRES_USER="${POSTGRES_USER:-postgres}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}" \
  -e PYTHONPATH=/opt/spark/scripts \
  "$SPARK_IMAGE" \
  /opt/spark/bin/spark-submit \
  --master "$SPARK_MASTER" \
  --conf spark.hadoop.fs.s3a.endpoint="$MINIO_ENDPOINT" \
  --conf spark.hadoop.fs.s3a.access.key="$MINIO_ACCESS_KEY" \
  --conf spark.hadoop.fs.s3a.secret.key="$MINIO_SECRET_KEY" \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
  --conf spark.hadoop.fs.s3.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions \
  --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
  --conf spark.sql.catalog.nessie.uri="$NESSIE_URI" \
  --conf spark.sql.catalog.nessie.ref="$NESSIE_REF" \
  --conf spark.sql.catalog.nessie.warehouse=s3://warehouse/ \
  --conf spark.sql.catalog.nessie.s3.endpoint="$MINIO_ENDPOINT" \
  --conf spark.sql.catalog.nessie.s3.path-style-access=true \
  --conf spark.driver.memory=512m \
  "/opt/spark/scripts/$SCRIPT_EXEC_REL"
docker volume rm "$VOL" >/dev/null 2>&1 || true
