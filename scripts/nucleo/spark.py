from os import environ as env

# conexao JDBC para ler a fonte sakila (layer bronze)
POSTGRES_URL = env.get("POSTGRES_JDBC_URL", "jdbc:postgresql://postgres:5432/sakila")
POSTGRES_USER = env.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = env.get("POSTGRES_PASSWORD", "postgres")

WAREHOUSE = "s3://warehouse/"


def _endpoints() -> dict:
    # padrao: rede do compose (resolve dentro dos containers jupyter e job);
    # do host use as portas publicadas (19120/9000)
    return {
        "minio_endpoint": env.get("MINIO_ENDPOINT", "http://minio:9000"),
        "minio_access_key": env.get("MINIO_ACCESS_KEY", "unidata"),
        "minio_secret_key": env.get("MINIO_SECRET_KEY", "supersenha"),
        "nessie_ref": env.get("NESSIE_REF", "dev"),
        "nessie_uri": env.get("NESSIE_URI", "http://nessie:19120/api/v1"),
    }


def cria_spark_session(app_name: str) -> "SparkSession":
    # import tardio: o modulo importa sem pyspark (self-check fora do container)
    from pyspark.sql import SparkSession

    e = _endpoints()
    spark = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.hadoop.fs.s3a.endpoint", e["minio_endpoint"])
        .config("spark.hadoop.fs.s3a.access.key", e["minio_access_key"])
        .config("spark.hadoop.fs.s3a.secret.key", e["minio_secret_key"])
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
            "org.projectnessie.spark.extensions.NessieSparkSessionExtensions",
        )
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config(
            "spark.sql.catalog.nessie.catalog-impl",
            "org.apache.iceberg.nessie.NessieCatalog",
        )
        .config("spark.sql.catalog.nessie.uri", e["nessie_uri"])
        .config("spark.sql.catalog.nessie.ref", e["nessie_ref"])
        .config("spark.sql.catalog.nessie.warehouse", WAREHOUSE)
        .config("spark.sql.catalog.nessie.s3.endpoint", e["minio_endpoint"])
        .config("spark.sql.catalog.nessie.s3.path-style-access", "true")
        .config("spark.driver.memory", "512m")
        .getOrCreate()
    )

    spark.sparkContext.setCheckpointDir("s3://warehouse/spark-checkpoints/")

    return spark
