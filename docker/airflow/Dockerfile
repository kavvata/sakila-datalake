FROM apache/airflow:3.3.1-python3.12

COPY docker/requirements-nbconvert.txt /requirements.txt
RUN pip install --no-cache-dir --requirement /requirements.txt \
    && python3 -c "import nbconvert"

# jupyter cai em /home/airflow/.local/bin (user-site do usuario airflow); sem esta linha no
# PATH o entrypoint so funciona via o fallback `${PYTHON} -m nbconvert` (testado).
ENV PATH=/home/airflow/.local/bin:${PATH}

# USER final nao-root; compose pode sobrescrever com user: root (entrypoint tem caminho setpriv)
USER airflow
