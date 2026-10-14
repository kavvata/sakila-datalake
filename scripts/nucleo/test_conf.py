# self-check do nucleo sem pyspark: python3 scripts/nucleo/test_conf.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.spark import POSTGRES_URL, WAREHOUSE, _endpoints  # noqa: E402

e = _endpoints()
assert e["nessie_uri"].startswith("http://") and e["nessie_uri"].endswith("/api/v1")
assert e["nessie_ref"] == "dev"
assert e["minio_endpoint"].startswith("http://")
assert e["minio_access_key"] and e["minio_secret_key"]
assert WAREHOUSE == "s3://warehouse/"
assert POSTGRES_URL.startswith("jdbc:postgresql://")
print("nucleo conf: ok")
