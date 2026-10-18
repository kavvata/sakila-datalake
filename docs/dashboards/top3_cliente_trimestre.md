# Dashboard: Top 3 Clientes por Trimestre

Metabase dashboard sobre a gold table `gold.top3_cliente_trimestre`
(produzida por `scripts/02_gold/cria_top3_customer_quarter_gold.ipynb`,
catalogo Nessie, lido via Trino).

Montado via MCP server do Metabase (server `local-mcp`). As instruções
abaixo reproduzem o fluxo exato usado; os ids numéricos (database,
tabela, campos, dashboard, cards) saem das próprias chamadas — use os
retornos de cada passo nos passos seguintes.

Resultado final: coleção raiz, 1 heading + 2 cards em largura total
empilhados (bar graph em cima, tabela de ranking embaixo).

## Pré-requisitos

1. DAG rodado de ponta a ponta — `gold.top3_cliente_trimestre` populada
   no Iceberg/Nessie (leitura: `ano, trimestre, ranking, cliente_id,
   nome_cliente, total_gasto`).
2. Metabase com datasource Trino apontando para o stack
   (`Datalake Sakila`, engine `starburst`).
3. Schema sincronizado: no Metabase, *Refresh data* no datasource
   (a conexão só enxerga `system` antes do sync).

## Passo 1 — Localizar database, tabela e ids de campos

```
mcp: browse_data {action: "list_databases"}            # anote o id do Trino
mcp: browse_data {action: "list_tables", database_id: <db>, schema: "gold", search: "top3"}
                                                       # anote o id da tabela
mcp: browse_data {action: "get_fields", table_ids: [<table>], response_format: "detailed"}
                                                       # anote o id de cada campo
```

Campos da tabela (use os ids que vierem no `get_fields`):

| Campo         | Tipo         |
|---------------|--------------|
| `ano`         | Integer      |
| `trimestre`   | Integer      |
| `ranking`     | Integer      |
| `cliente_id`  | Integer      |
| `nome_cliente`| Text         |
| `total_gasto` | Decimal(15,2)|

Nas consultas abaixo, `<db>`, `<table>` e `<f:campo>` representam os ids
anotados (ex.: `["field", {}, <f:ano>]`).

## Passo 2 — Criar o dashboard (shell vazio)

```
mcp: dashboard_write {
  method: "create", name: "Top 3 Clientes por Trimestre",
  collection_id: "root", width: "full",
  description: "Gold top3_cliente_trimestre — os 3 clientes que mais
                gastaram por ano e trimestre"
}
```

Anote o `id` do dashboard retornado.

## Passo 3 — Card de bar graph (gasto por período)

X = `ano` + `trimestre` combinados (`2005-T2`), Y = soma do `total_gasto`.
O concat precisa de `text(...)`: o Trino rejeita `concat(integer, varchar)`.

Execute primeiro para validar (e obter o `query_handle`):

```
mcp: execute_query {query: {
  "lib/type": "mbql/query", "database": <db>,
  "stages": [{"lib/type": "mbql.stage/mbql", "source-table": <table>,
    "expressions": {
      "periodo": ["concat", {},
                  ["text", {}, ["field", {}, <f:ano>]],
                  "-T",
                  ["text", {}, ["field", {}, <f:trimestre>]]]
    },
    "aggregation": [["sum", {"name": "total_gasto",
                             "display-name": "Total gasto"},
                     ["field", {}, <f:total_gasto>]]],
    "breakout": [["expression", {}, "periodo"]]}
}}
```

Resultado esperado: 1 linha por período (ex. `2005-T2 → 183.65`).
Salve como pergunta **dentro do dashboard**:

```
mcp: question_write {method: "create", name: "Gasto dos top 3 clientes por
  trimestre", query_handle: "<handle>", dashboard_id: <dash>, display: "bar"}
```

## Passo 4 — Card de tabela (ranking com medalhas)

Colunas: `periodo` | `medalha` (🥇🥈🥉 via `case` no `ranking`) |
`nome_cliente`. O `order-by` usa campos não exibidos (`ano`, `trimestre`,
`ranking`) para manter a ordem do ranking.

```
mcp: execute_query {query: {
  "lib/type": "mbql/query", "database": <db>,
  "stages": [{"lib/type": "mbql.stage/mbql", "source-table": <table>,
    "expressions": {
      "periodo": ["concat", {},
                  ["text", {}, ["field", {}, <f:ano>]], "-T",
                  ["text", {}, ["field", {}, <f:trimestre>]]],
      "medalha": ["case", {},
                  [["=", {}, ["field", {}, <f:ranking>], 1], "🥇"],
                  [["=", {}, ["field", {}, <f:ranking>], 2], "🥈"],
                  [["=", {}, ["field", {}, <f:ranking>], 3], "🥉"],
                  "-"]
    },
    "fields": [["expression", {}, "periodo"],
               ["expression", {}, "medalha"],
               ["field", {}, <f:nome_cliente>]],
    "order-by": [["asc", {}, ["field", {}, <f:ano>]],
                 ["asc", {}, ["field", {}, <f:trimestre>]],
                 ["asc", {}, ["field", {}, <f:ranking>]]]}
}}
```

```
mcp: question_write {method: "create", name: "Ranking top 3 clientes por
  trimestre", query_handle: "<handle>", dashboard_id: <dash>, display: "table"}
```

Anote os `id`s dos dois cards. O passo 5 precisa dos **dashcard** ids (os
dos dashcards que o `question_write` criou) — leia-os no read-back
`get_content {items: [{type: "dashboard", id: <dash>}], include: ["layout"]}`.

## Passo 5 — Layout

Grid de 24 colunas. Heading + os dois cards (já criados como dashcards no
passo 4 — mover, não re-adicionar) em largura total, empilhados:

```
mcp: dashboard_write {method: "update", id: <dash>, ops: [
  {"op": "add_heading", "id": -1,
   "text": "Top 3 clientes por trimestre — gold.top3_cliente_trimestre",
   "position": {"row": 0, "col": 0}, "size": {"size_x": 24, "size_y": 1}},
  {"op": "move", "dashcard_id": <dc_bar>, "position": {"row": 1, "col": 0}},
  {"op": "resize", "dashcard_id": <dc_bar>, "size": {"size_x": 24, "size_y": 6}},
  {"op": "move", "dashcard_id": <dc_tabela>, "position": {"row": 7, "col": 0}},
  {"op": "resize", "dashcard_id": <dc_tabela>, "size": {"size_x": 24, "size_y": 6}}
]}
```

## Passo 6 — Verificar (sempre)

```
mcp: get_content {items: [{type: "dashboard", id: <dash>}],
                  include: ["layout"]}
mcp: get_content {items: [{type: "question", id: <card_bar>},
                          {type: "question", id: <card_tabela>}],
                  include: ["definition"]}
```

Confirme: 3 dashcards (heading + 2 cards, `size_x: 24`, sem sobreposição)
e as definições salvas contendo `periodo`/`medalha`.

## Pegadinhas aprendidas (não pular)

1. **Escrevas podem não persistir**: `dashboard_write`/`question_write`
   às vezes respondem com um "preview" idêntico ao sucesso real sem
   gravar nada (ex.: ops com `add_parameter`/`wire_parameter`, quando a
   permissão de mapping por campo falha). **Sempre faça read-back com
   `get_content` depois de cada write.**
2. **`question_write` com `dashboard_id` já cria o dashcard** na
   dashboard. Fazer `add_card` depois duplica o card (por isso o passo 5
   usa `move`/`resize`) — se duplicar assim mesmo,
   `{"op": "remove", "dashcard_id": <id>}` nos extras (ids visíveis no
   read-back; o `remove` aceita só `op` + `dashcard_id`).
3. **Trino + `concat`**: argumentos numéricos precisam de `["text", {}, …]`.
4. **Parâmetro/filtro "Ano"**: `add_parameter` + `wire_parameter`
   (`number/=`, campo `ano`, `autowire: true`) é bloqueado no save real
   pela checagem de permissão de mapping do token MCP. Adicionar pela UI
   do Metabase (⚙️ *Filters* → *Ano*, numeric equality) resolve.
5. O proxy MCP exige **todos** os parâmetros de cada tool (inclusive
   `null` para os opcionais); ops do `dashboard_write` só aceitam as
   chaves do tipo de op que estão executando (ex.: `remove` não aceita
   `tab`/`position` extras). Args grandes/aninhados (ex.: a query `case`
   do passo 4) às vezes chegam mal-serializados (`args: must be object` /
   `Invalid args JSON`) — nesse caso, monte o JSON, valide e envie como
   **string** pela tool `mcp` (aceita JSON string).
6. **`default: null` em `add_parameter` falha na validação** do proxy
   ("must match exactly one schema in oneOf"). Se precisar de default,
   passe um valor real (ex.: `2005`); para filtro sem default, crie o
   parâmetro e ajuste depois pela UI.
