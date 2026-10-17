# Metabase com o driver Dremio (Baoqi/metabase-dremio-driver) na raiz de /plugins.
# A partir de 0.65 o Metabase so adiciona jars a classpath quando estao na
# raiz de /plugins (dir padrao do MB_PLUGINS_DIR, sem recursao em subdirs);
# /usr/local/metabase/drivers deixou de ser varrido.
# O jar e um driver Metabase completo (metabase-plugin.yaml + JDBC do Dremio),
# fixado em docker/metabase/dremio.metabase-driver.jar (1.5.0, requer
# Metabase >= 0.51.0) — baixar de
# https://github.com/Baoqi/metabase-dremio-driver/releases
FROM metabase/metabase:v0.65.0.x

COPY docker/metabase/dremio.metabase-driver.jar /plugins/
