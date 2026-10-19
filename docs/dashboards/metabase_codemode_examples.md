# Metabase MCP (`sakila_metabase`) — scripts prontos para codemode

Scripts validados na construção do dashboard `Top 3 Clientes por Trimestre`
(veja `top3_cliente_trimestre.md`). Cada bloco é um **script codemode
independente** — o escopo não é compartilhado entre scripts, então os ids
viajam com `store(key, value)` / `load(key)`. Cole o bloco inteiro como
`code` do tool `codemode`.

**Nenhum id é hardcoded** — todos os ids (database, tabela, campos,
dashboard, cards, dashcards) são resolvidos em runtime pelos scripts 1–9
e passam entre eles via `store`. Contrato de chaves:

| store key | Gravada em | Usada em |
|---|---|---|
| `db.id` | 1 | 2, 3, 5, 7 |
| `table.id` | 2 | 3, 5, 7 |
| `f.<campo>` (uma por campo) | 3 | 5, 7 |
| `dash.id` | 4 | 6, 8, 9, 10, 11, 12 |
| `handle.bar` / `handle.tabela` | 5 / 7 | 6 / 8 |
| `card.bar` / `card.tabela` | 6 / 8 | 11 |
| `dashcard.bar` / `dashcard.tabela` | 9 | 10 |
| `dashcard.excedente` (só se houver duplicata) | read-back do 9 | 12 |

Regras rápidas:

- O retorno é texto com o JSON dentro de um bloco `<data boundary="…">…</data>` — o helper `parse` de cada script extrai.
- **Toda chave é obrigatória** em toda tool e em todo `op` do `dashboard_write`, mesmo com `null`. Chave ausente = erro de validação (a mensagem nomeia a que falta).
- `question_write` com `dashboard_id` **já cria o dashcard** — depois só `move`/`resize`; `add_card` duplica.
- Sempre read-back com `get_content` depois de cada write (o `create` de dashboard não é atômico).

---

## 1 — Localizar o database

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__browse_data({
  action: "list_databases", database_id: null, fields: null,
  include_hidden: null, limit: null, offset: null,
  response_format: null, schema: null, search: null, table_ids: null
}));
const db = r.data.find(d => d.name === "Datalake Sakila");
store("db.id", db.id);
console.log(db.id, db.name, db.engine);
```

## 2 — Localizar a tabela

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dbId = load("db.id");
const r = parse(await tools.mcp__sakila_metabase__browse_data({
  action: "list_tables", database_id: dbId, fields: null,
  include_hidden: null, limit: null, offset: null,
  response_format: null, schema: "gold", search: "top3", table_ids: null
}));
store("table.id", r.data[0].id);
console.log(r.data);
```

## 3 — Ler os ids dos campos

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dbId = load("db.id"), tblId = load("table.id");
const r = parse(await tools.mcp__sakila_metabase__browse_data({
  action: "get_fields", database_id: dbId, fields: null,
  include_hidden: null, limit: null, offset: null,
  response_format: "concise", schema: null, search: null, table_ids: [tblId]
}));
// grava "f.<nome_do_campo>" para cada campo
for (const f of r.tables[0].fields) {
  store("f." + f.name, f.id);
  console.log(f.name, f.id, f.base_type);
}
```

## 4 — Criar o dashboard (shell vazio)

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__dashboard_write({
  method: "create",
  name: "Top 3 Clientes por Trimestre",
  collection_id: "root",
  width: "full",
  description: "Gold top3_cliente_trimestre — os 3 clientes que mais gastaram por ano e trimestre",
  id: null, archived: null, auto_apply_filters: null, cache_ttl: null,
  clear: null, collection_position: null, ops: null, validate_only: null
}));
store("dash.id", r.id);
console.log("dash", r.id);
```

Se um `create` anterior falhou no meio, **não crie de novo** (duplica):
leia por nome (`browse_collection`/`search`) e finalize com `method: "update"`.

## 5 — Executar a query do bar graph (e obter o `query_handle`)

X = `nome_cliente`, Y = soma do `total_gasto`, filtrado por `ranking = 1`
(só o 1º lugar de cada período).

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dbId = load("db.id"), tblId = load("table.id");
const fRank = load("f.ranking"), fNome = load("f.nome_cliente"),
      fGasto = load("f.total_gasto");
const q = { "lib/type": "mbql/query", "database": dbId, "stages": [{
  "lib/type": "mbql.stage/mbql", "source-table": tblId,
  "filters": [["=", {}, ["field", {}, fRank], 1]],
  "aggregation": [["sum", { "name": "total_gasto", "display-name": "Total gasto" },
                   ["field", {}, fGasto]]],
  "breakout": [["field", {}, fNome]]
}]};
const r = parse(await tools.mcp__sakila_metabase__execute_query({
  query: q, query_handle: null, cursor: null, prompt: null,
  row_limit: null, validate_only: null
}));
store("handle.bar", r.query_handle);
console.log(r.rows); // esperado: [["ELEANOR HUNT",188.6],["JUNE CARROLL",64.87],["MILDRED BAILEY",9.98]]
```

## 6 — Salvar o bar graph como card do dashboard

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__question_write({
  method: "create",
  name: "Gasto dos top 1 clientes",
  query_handle: load("handle.bar"),
  query: null,
  native: null,
  dashboard_id: load("dash.id"),   // cria o card E o dashcard
  collection_id: null,
  display: "bar",
  // eixo Y em USD: chaves de column_settings são ARRAYS JSON-encoded em string
  visualization_settings: {
    "column_settings": {
      '["name","total_gasto"]': {
        "number_style": "currency", "currency": "USD", "decimals": 2
      }
    }
  },
  id: null, card_type: null, description: null,
  cache_ttl: null, column_metadata: null,
  archived: null, clear: null, collection_position: null
}));
store("card.bar", r.id);
console.log("card bar", r.id);
```

## 7 — Executar a query da tabela de ranking (medalhas via `case`)

O `concat` precisa de `text(...)` — o Trino rejeita `concat(integer, varchar)`.

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dbId = load("db.id"), tblId = load("table.id");
const fAno = load("f.ano"), fTris = load("f.trimestre"),
      fRank = load("f.ranking"), fNome = load("f.nome_cliente");
const periodoExpr = ["concat", {},
  ["text", {}, ["field", {}, fAno]], "-T",
  ["text", {}, ["field", {}, fTris]]];
const medalhaExpr = ["case", {},
  [["=", {}, ["field", {}, fRank], 1], "🥇"],
  [["=", {}, ["field", {}, fRank], 2], "🥈"],
  [["=", {}, ["field", {}, fRank], 3], "🥉"],
  "-"];
const q = { "lib/type": "mbql/query", "database": dbId, "stages": [{
  "lib/type": "mbql.stage/mbql", "source-table": tblId,
  "expressions": { "periodo": periodoExpr, "medalha": medalhaExpr },
  "fields": [["expression", {}, "periodo"], ["expression", {}, "medalha"],
             ["field", {}, fNome]],
  // order-by usa campos não exibidos para preservar a ordem do ranking
  "order-by": [["asc", {}, ["field", {}, fAno]],
               ["asc", {}, ["field", {}, fTris]],
               ["asc", {}, ["field", {}, fRank]]]
}]};
const r = parse(await tools.mcp__sakila_metabase__execute_query({
  query: q, query_handle: null, cursor: null, prompt: null,
  row_limit: null, validate_only: null
}));
store("handle.tabela", r.query_handle);
console.log(r.rows); // esperado: 9 linhas, 🥇🥈🥉 por período
```

## 8 — Salvar a tabela de ranking como card do dashboard

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__question_write({
  method: "create",
  name: "Ranking top 3 clientes por trimestre",
  query_handle: load("handle.tabela"),
  query: null,
  native: null,
  dashboard_id: load("dash.id"),
  collection_id: null,
  display: "table",
  id: null, card_type: null, description: null,
  visualization_settings: null, cache_ttl: null, column_metadata: null,
  archived: null, clear: null, collection_position: null
}));
store("card.tabela", r.id);
console.log("card tabela", r.id);
```

## 9 — Ler os ids dos dashcards (o layout os precisa)

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__get_content({
  items: [{ type: "dashboard", id: load("dash.id"), fields: null }],
  include: ["layout"],
  response_format: null
}));
for (const dc of r.results[0].dashcards.filter(d => d.kind === "card")) {
  const key = dc.card.name.startsWith("Gasto") ? "dashcard.bar"
            : dc.card.name.startsWith("Ranking") ? "dashcard.tabela"
            : "dashcard.outro";
  store(key, dc.id);
  console.log(key, "=", dc.id, "-> card", dc.card.id, dc.card.name);
}
```

## 10 — Layout: heading + 2 cards full-width empilhados

Os ids dos dashcards vêm do `store` gravado no script 9 (rode 9 antes).
Todo `op` leva **todas** as chaves do seu tipo (`null` nas opcionais).

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dcBar = load("dashcard.bar"), dcTabela = load("dashcard.tabela");
const r = parse(await tools.mcp__sakila_metabase__dashboard_write({
  method: "update",
  id: load("dash.id"),
  name: null, collection_id: null, width: null, description: null,
  archived: null, auto_apply_filters: null, cache_ttl: null,
  clear: null, collection_position: null, validate_only: null,
  ops: [
    { "op": "add_heading", "id": -1,
      "text": "Top 3 clientes por trimestre — gold.top3_cliente_trimestre",
      "position": { "row": 0, "col": 0 }, "size": { "size_x": 24, "size_y": 1 },
      "inline_parameters": null, "tab": null },
    { "op": "move", "dashcard_id": dcBar,
      "position": { "row": 1, "col": 0 }, "tab": null },
    { "op": "resize", "dashcard_id": dcBar, "size": { "size_x": 24, "size_y": 6 } },
    { "op": "move", "dashcard_id": dcTabela,
      "position": { "row": 7, "col": 0 }, "tab": null },
    { "op": "resize", "dashcard_id": dcTabela, "size": { "size_x": 24, "size_y": 6 } }
  ]
}));
console.log(JSON.stringify(r.dashcards, null, 1));
```

`add_heading`/`add_card`/`add_text`… pedem `id` negativo próprio (servidor
atribui o real no save); `move`/`resize`/`remove` apontam para dashcard
existente por id real.

## 11 — Verificação final (sempre)

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const dash = parse(await tools.mcp__sakila_metabase__get_content({
  items: [{ type: "dashboard", id: load("dash.id"), fields: null }],
  include: ["layout"],
  response_format: null
}));
console.log(JSON.stringify(dash.results[0].dashcards, null, 1));
const qs = parse(await tools.mcp__sakila_metabase__get_content({
  items: [{ type: "question", id: load("card.bar"), fields: null },
          { type: "question", id: load("card.tabela"), fields: null }],
  include: ["definition"],
  response_format: null
}));
for (const it of qs.results)
  console.log(it.id, it.name, JSON.stringify(it.definition).length > 0 ? "def ok" : "SEM DEFINIÇÃO");
```

Confira: 3 dashcards (heading + 2 cards), todos `size_x: 24`, sem
sobreposição de row/col, e as definições com as expressões `periodo`
(concat de `ano`+`trimestre`) e `medalha` (case sobre `ranking`).

## 12 — Corrigir dashcard duplicado (se aconteceu)

Se um `add_card` duplicou um card, leia o read-back (script 9), grave
`store("dashcard.excedente", <id>)` com o excedente e remova — `remove`
aceita **só** `op` + `dashcard_id`:

```js
const parse = (res) => {
  const text = res.content.map(c => c.text || "").join("");
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON in: " + text.slice(0, 400));
  return JSON.parse(m[0]);
};
const r = parse(await tools.mcp__sakila_metabase__dashboard_write({
  method: "update",
  id: load("dash.id"),
  name: null, collection_id: null, width: null, description: null,
  archived: null, auto_apply_filters: null, cache_ttl: null,
  clear: null, collection_position: null, validate_only: null,
  ops: [{ "op": "remove", "dashcard_id": load("dashcard.excedente") }]
}));
console.log(JSON.stringify(r.dashcards));
```

---

## Cheatsheet — chaves obrigatórias por tool

`null` é valor válido; chave ausente não.

- **browse_data**: `action`, `database_id`, `fields`, `include_hidden`, `limit`, `offset`, `response_format`, `schema`, `search`, `table_ids`
- **execute_query**: `query`, `query_handle`, `cursor`, `prompt`, `row_limit`, `validate_only`
- **question_write**: `method`, `name`, `id`, `query_handle`, `query`, `native`, `dashboard_id`, `collection_id`, `display`, `card_type`, `description`, `visualization_settings`, `cache_ttl`, `column_metadata`, `archived`, `clear`, `collection_position`
- **dashboard_write**: `method`, `id`, `name`, `collection_id`, `width`, `description`, `archived`, `auto_apply_filters`, `cache_ttl`, `clear`, `collection_position`, `ops`, `validate_only`
- **get_content**: `items` (cada item: `type`, `id`, `fields`), `include`, `response_format`

Ops de layout (chaves por tipo):

| op | chaves |
|---|---|
| `add_heading` | `op, id, text, position, size, inline_parameters, tab` |
| `add_card` | `op, id, card_id, position, size, inline_parameters, tab, series` |
| `move` | `op, dashcard_id, position, tab` |
| `resize` | `op, dashcard_id, size` (sem `position`) |
| `remove` | `op, dashcard_id` |

Antes do primeiro uso de temas novos, leia a doc no servidor:
`await tools.mcp__sakila_metabase__learn({topic: "<tema>", reference: null})`
— temas: `query-dialect`, `native-parameters`, `dashboard-filters`,
`dashboard-layout`, `visualization-settings`.

Pegadinha extra de parâmetros: `add_parameter` com `default: null` falha na
validação (oneOf) — passe um valor real (ex.: `2005`) ou crie sem default e
ajuste pela UI. E filtro "Ano" via `wire_parameter` pode ser bloqueado no
save real por permissão de mapping por campo (`validate_only` limpo não
garante o save) — a UI do Metabase resolve.
