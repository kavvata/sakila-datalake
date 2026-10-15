FROM python:3.12-slim

# Imagem dedicada a conversão notebook->python (make convert)
COPY docker/requirements-nbconvert.txt /requirements.txt
RUN pip install --no-cache-dir --requirement /requirements.txt \
    && python -c "import nbconvert"

USER nobody
WORKDIR /workspace
