#!/bin/sh
set -e

# nbconvert (user-site) fica em /home/airflow/.local, entao HOME=/home/airflow
# (a imagem sozinha traria HOME=/root e o import nao encontraria).
export HOME=/home/airflow
HOST_UID="${HOST_UID:-1000}"
AIRFLOW_UID="${AIRFLOW_UID:-50000}"

PYTHON="/home/airflow/.local/bin/python3"
command -v "${PYTHON}" >/dev/null 2>&1 || PYTHON=python3
export PYTHON

nbconvert() {
  if command -v jupyter >/dev/null 2>&1; then
    jupyter nbconvert "$@"
  else
    "${PYTHON}" -m nbconvert "$@"
  fi
}

# fallback de seguranca: a imagem ja traz jupyter/nbconvert (Dockerfile)
if ! "${PYTHON}" -c "import nbconvert" >/dev/null 2>&1; then
  echo "[entrypoint] aviso: nbconvert ausente, instalando via pip..."
  if [ -f /requirements.txt ]; then
    "${PYTHON}" -m pip install --no-cache-dir --requirement /requirements.txt
  else
    "${PYTHON}" -m pip install --no-cache-dir jupyter==1.1.1 nbconvert==7.17.1
  fi
fi

SCRIPTS_DIR="/opt/spark/scripts"
[ -d "${SCRIPTS_DIR}" ] || SCRIPTS_DIR="${UNIDATA_REPO_DIR:-.}/scripts"

if [ -d "${SCRIPTS_DIR}" ]; then
  echo "[entrypoint] convertendo notebooks -> python em ${SCRIPTS_DIR}"
  export HOST_UID
  PARALLEL="${NBCONVERT_PARALLEL:-$(nproc 2>/dev/null || echo 2)}"
  find "${SCRIPTS_DIR}" -name "*.ipynb" -not -path "*/.ipynb_checkpoints/*" -print0 |
    xargs -0 -P "${PARALLEL}" -I {} \
      sh -c 'if command -v jupyter >/dev/null 2>&1; then
               jupyter nbconvert --to python "$0"
             else
               "${PYTHON:-python3}" -m nbconvert --to python "$0"
             fi || echo "[entrypoint] AVISO: falha em $0" >&2' {}
  if [ "$(id -u)" = "0" ]; then
    find "${SCRIPTS_DIR}" -name "*.ipynb" -not -path "*/.ipynb_checkpoints/*" -print0 |
      xargs -0 -I {} \
        sh -c 'out="${0%.ipynb}.py"; [ -f "${out}" ] && chown "${HOST_UID}:${HOST_UID}" "${out}"' {}
  fi
else
  echo "[entrypoint] aviso: pasta de scripts nao encontrada, pulando nbconvert" >&2
fi

# Garante que o usuario do airflow (gid do grupo docker do host) acesse o
# docker.sock montado (no host: 664 root:docker) — sem alterar nada no host.
DOCKER_SOCK=/var/run/docker.sock
AIRFLOW_GID=0
if [ -S "${DOCKER_SOCK}" ]; then
  DOCKER_GID=$(stat -c %g "${DOCKER_SOCK}" 2>/dev/null || echo 0)
  [ "${DOCKER_GID}" != "0" ] && AIRFLOW_GID="${DOCKER_GID}"
fi

# Se já estamos como o usuario do airflow (USER da imagem), executa direto;
# caso contrario (root via compose) faz o drop de privilegio com setpriv.
if [ "$(id -un)" = "airflow" ]; then
  exec /bin/bash "$@"
fi

exec setpriv --reuid="${AIRFLOW_UID}" --regid="${AIRFLOW_GID}" --init-groups /bin/bash "$@"

