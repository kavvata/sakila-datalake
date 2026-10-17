# Sakila Datalake

Este projeto roda um fluxo de dados completo no seu computador.
Os dados vêm do Sakila, um banco de dados de exemplo do PostgreSQL.
O Sakila simula uma locadora de vídeos: clientes, filmes, locações e pagamentos.
Os dados vão do banco para um data lake.
Depois, você consulta esses dados pela web.
Todos os serviços rodam em containers Docker.

## 1. O que você precisa

- Docker instalado. Cheque com `docker --version`
- 8 GB de RAM livres
- Um terminal com o comando `make` (já vem no macOS, no Linux e no WSL)

## 2. Subir o projeto

Abra o terminal na pasta do projeto.
Rode os comandos, um por um, nesta ordem:

```bash
cp .env.example .env
make build-images
make up
```

`make build-images` demora alguns minutos. Rode uma vez.
`make up` sobe todos os serviços.
Se você já subiu o projeto antes, pule para `make up`.

Cheque o status:

```bash
docker compose ps
```

Todos os serviços devem aparecer como `running`.
Se algum ainda está subindo, aguarde 1 minuto e rode o comando de novo.

## 3. Usar as interfaces web

### Airflow — o fluxo de dados

1. Abra http://localhost:8080
2. Entre com o usuário `airflow` e a senha `airflow`
3. Clique no fluxo `aplica_elt_sakila` (a interface chama de DAG)
4. O fluxo começa pausado. Clique em **Unpause**
5. Clique em **Trigger DAG**
6. Aguarde. A primeira execução demora alguns minutos
7. Quando todas as tarefas ficam verdes, os dados estão carregados

### Metabase — relatórios

1. Abra http://localhost:3000
2. Na primeira vez, crie sua conta

### Dremio — consultas SQL

1. Abra http://localhost:9047
2. Na primeira vez, crie sua conta

## 4. Parar o projeto

```bash
make down
```

Isso para todos os serviços.
Os dados ficam salvos.
Para subir de novo, rode `make up` (seção 2).
