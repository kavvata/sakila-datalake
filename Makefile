# Cadeia de imagens (base -> spark -> jupyter) e gerencia do compose.
BASE_TAG := 4.1.2

.PHONY: build-images up up-nb down

build-images:
	docker build -t unidata-spark-base:$(BASE_TAG) -f docker/base/Dockerfile .
	docker build -t unidata-spark:$(BASE_TAG) -f docker/spark/Dockerfile .
	docker build -t unidata-jupyter:$(BASE_TAG) -f docker/jupyter/Dockerfile .

up:
	docker compose up -d

up-nb:
	docker compose up -d jupyter

down:
	docker compose down
