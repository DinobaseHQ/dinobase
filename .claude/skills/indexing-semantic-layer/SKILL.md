---
name: indexing-semantic-layer
description: Build or update the semantic layer for a Dinobase source — checks what's already annotated, then fills gaps and rebuilds only what's missing or incomplete.
argument-hint: <source_name>
---

# Indexing the Semantic Layer

The source to index: **$ARGUMENTS**

Launch a general-purpose subagent to audit existing annotations and fill every gap.

Provide this prompt to the subagent:

---

You are building the semantic layer for the Dinobase source **$ARGUMENTS**.

Your job is to audit what's already annotated, then fill every gap — table descriptions, column docs, PII flags, and relationships. Don't overwrite annotations that are already good. Only add or fix what's missing or wrong.

### Step 0: Check the input schema

```bash
uv run dinobase annotate --input-schema
```

This shows the exact JSON format accepted by the `annotate` command.

### Step 1: Audit existing annotations

Run all four checks and note what's missing:

```bash
# Tables with no description
uv run dinobase query "SELECT table_name, row_count FROM _dinobase.tables WHERE schema_name = '$ARGUMENTS' AND description IS NULL ORDER BY row_count DESC"

# Tables that already have descriptions (skip these unless wrong)
uv run dinobase query "SELECT table_name, description FROM _dinobase.tables WHERE schema_name = '$ARGUMENTS' AND description IS NOT NULL"

# Columns already annotated
uv run dinobase query "SELECT table_name, column_name, description FROM _dinobase.columns WHERE schema_name = '$ARGUMENTS' AND description IS NOT NULL ORDER BY table_name, column_name"

# Existing relationships
uv run dinobase query "SELECT from_table, from_column, to_table, to_column, cardinality, description FROM _dinobase.relationships WHERE from_schema = '$ARGUMENTS' OR to_schema = '$ARGUMENTS'"

# Existing KV metadata (pii, deprecated, owner, etc.)
uv run dinobase query "SELECT table_name, column_name, key, value FROM _dinobase.metadata WHERE schema_name = '$ARGUMENTS' ORDER BY table_name, column_name, key"
```

### Step 2: Explore gaps

For every table that is missing a description, or any table that has unannotated columns worth documenting, explore its schema and sample data:

```bash
uv run dinobase query "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '$ARGUMENTS' AND table_name = '<table>' ORDER BY ordinal_position"
uv run dinobase query "SELECT * FROM \"$ARGUMENTS\".\"<table>\" LIMIT 3"
```

Understand:
- What entity or event does this table represent?
- Which columns carry meaningful business data vs structural noise (`*_url`, `node_id`, `_dlt_*`)?
- Which columns contain personal data (email, name, phone, IP, user ID)?
- Which columns are foreign keys (`*_id`, `*__id`, `_dlt_parent_id`, `_dlt_root_id`)?
- Are any existing relationships missing from the graph?

### Step 3: Write only what's missing

After exploring, write a single `dinobase annotate` call with a JSON array containing **only the gaps** — skip anything that already has a correct annotation. You can mix annotation and relationship items in the same array:

```bash
uv run dinobase annotate '[
  {"target": "$ARGUMENTS.<table>", "key": "description", "value": "What this table contains"},
  {"target": "$ARGUMENTS.<table>.<column>", "key": "description", "value": "What this column means"},
  {"target": "$ARGUMENTS.<table>.<column>", "key": "pii", "value": "true"},
  {"from_table": "$ARGUMENTS.<table>", "from_column": "<col>", "to_table": "$ARGUMENTS.<other_table>", "to_column": "id", "cardinality": "one_to_many", "description": "Each X belongs to one Y"}
]'
```

### Step 4: Verify completeness

Check that no gaps remain:

```bash
# Tables still missing descriptions
uv run dinobase query "SELECT table_name FROM _dinobase.tables WHERE schema_name = '$ARGUMENTS' AND description IS NULL"

# Spot-check the main table — should have description, related_tables, annotated columns
uv run dinobase describe $ARGUMENTS.<main_table> 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('description:', d.get('description'))
print('related_tables:', len(d.get('related_tables', [])))
print('annotated columns:', sum(1 for c in d['columns'] if c.get('description')), '/', len(d['columns']))
"
```

Report back what was added and what (if anything) couldn't be determined from the data.

---

### Annotation rules

- **Every table gets a description** — even junction/child tables
- **Skip noisy columns** — `*_url`, `node_id`, `_dlt_load_id`, `_dlt_id`, `_dlt_list_idx`
- **Always annotate join keys** — `_dlt_parent_id`: "Join key to X._dlt_id"; FK columns like `customer_id`: "References customers.id"
- **Be specific** — "Customer's billing email" not "Email"; "ISO 8601, used for incremental sync" not "Updated at"
- **Flag all PII** — email, name, phone, IP, any user-identifying field
- **Map every relationship** — parent-child (dlt), FK joins, cross-source shared columns
- **Don't overwrite good annotations** — only include items in the JSON array that were missing in Step 1
