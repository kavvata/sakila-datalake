# Cadeia de imagens (base -> spark -> jupyter) e gerencia do compose.
BASE_TAG := 4.1.2
CONCURRENCY ?= $(shell nproc)

.PHONY: build-images up up-nb down sync-raw nuke convert docker-nbconvert

build-images:
	docker build -t unidata-spark-base:$(BASE_TAG) -f docker/base/Dockerfile .
	docker build -t unidata-spark:$(BASE_TAG) -f docker/spark/Dockerfile .
	docker build -t unidata-jupyter:$(BASE_TAG) -f docker/jupyter/Dockerfile .
	docker build -t unidata-metabase:$(BASE_TAG) -f docker/metabase/Dockerfile .

up:
	docker compose up -d

up-nb:
	docker compose up -d jupyter

down:
	docker compose down

## Sincroniza ./raw com o bucket 'raw' do MinIO (mc na imagem do compose; nao remove objetos extra no bucket)
sync-raw:
	docker run --rm --entrypoint sh --network datalake-example_default -v "$$PWD/raw:/raw:ro" docker.io/pgsty/mc:RELEASE.2026-03-13T08-57-32Z -c "mc alias set local http://minio:9000 '$${MINIO_ACCESS_KEY:-unidata}' '$${MINIO_SECRET_KEY:-supersenha}' && mc mb --ignore-existing local/raw && mc mirror /raw local/raw"

## Conversão local notebooks→python em paralelo (mesma lógica do CI)
convert: docker-nbconvert
	@UID_S=$$(stat -c %u scripts); export UID_S; GID_S=$$(stat -c %g scripts); export GID_S; \
	find scripts -name "*.ipynb" -not -path "*/.ipynb_checkpoints/*" -print0 | \
		xargs -0 -P "$(CONCURRENCY)" -I{} \
		sh -c 'docker run --rm --user "$$UID_S:$$GID_S" -v "$$PWD:/workspace" -w /workspace unidata/nbconvert jupyter nbconvert --to python "/workspace/{}"' || exit 1

## Garante a imagem unidata/nbconvert (build somente se ausente)
docker-nbconvert:
	@docker image inspect unidata/nbconvert >/dev/null 2>&1 \
		|| docker build -q -t unidata/nbconvert -f docker/nbconvert/Dockerfile .

nuke:
	docker compose down
	docker volume ls -q --filter name=datalake-example_ | grep -v dremio_data | xargs -r docker volume rm
