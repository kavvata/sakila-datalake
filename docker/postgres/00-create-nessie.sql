-- roda em /postgres (DB inicial) durante o primeiro init do container;
-- cria user+db do version store JDBC do Nessie.
CREATE ROLE nessie LOGIN PASSWORD 'nessie';
CREATE DATABASE "nessie-postgres" OWNER nessie;
