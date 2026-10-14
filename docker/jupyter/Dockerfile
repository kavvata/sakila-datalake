ARG SPARK_IMAGE=unidata-spark:4.1.2
FROM $SPARK_IMAGE

USER root

# Versoes alinhadas a docker/requirements-nbconvert.txt (contexto deste build nao enxerga a raiz)
COPY docker/requirements-nbconvert.txt /requirements.txt
RUN pip install --no-cache-dir --requirement /requirements.txt

# Create a user matching the host UID (1000) so Spark/Hadoop can resolve it
RUN useradd -m -u 1000 -g spark -d /home/jupyter jupyter

ENV JUPYTER_RUNTIME_DIR=/tmp/jupyter-runtime
USER jupyter

ENTRYPOINT ["jupyter", "notebook", "--ip=0.0.0.0", "--no-browser", "--port=8888", "--NotebookApp.token=''", "--ServerApp.websocket_ping_interval=30000", "--ServerApp.websocket_ping_timeout=30000"]
