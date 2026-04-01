---
title: Development
description: Set up a development environment, run tests, and contribute to Dinobase.
---

## Setup

```bash
git clone https://github.com/DinobaseHQ/dinobase
cd dinobase
pip install -e ".[dev]"
```

Dev dependencies: `pytest`, `pytest-asyncio`.

## Running tests

```bash
pytest
```

Tests use sample parquet data loaded into an in-memory DuckDB instance.

147 tests covering the full stack: database, query engine, mutations, sync, CLI, MCP, and YAML connectors.

### Test structure

```
tests/
  conftest.py              # Fixtures (sample_db with Stripe + HubSpot data)
  test_db.py               # DinobaseDB: metadata, sync logging, schema introspection
  test_query_engine.py     # QueryEngine: queries, joins, aggregations, describe
  test_mutations.py        # MutationEngine: preview, confirm, cancel, batch
  test_cli.py              # CLI commands: init, add, sync, query, status
  test_mcp.py              # MCP server: tools, instructions
  test_yaml_source.py      # YAML-to-dlt translation, pagination, auth
  test_write_client.py     # Write-back to source APIs
```

### Key fixtures

**`sample_db`** -- A DinobaseDB loaded with sample Stripe and HubSpot data:

- Stripe: customers, subscriptions, charges, invoices
- HubSpot: contacts, companies, deals
- Metadata extracted from Stripe's OpenAPI spec
- ~200 people with ~80% email overlap for cross-source join testing

## Sample data

Generate realistic test data:

```bash
pip install faker
python scripts/generate_sample_data.py
```

Creates 7 parquet files in `sample_data/`:

| File | Records | Notes |
|------|---------|-------|
| `stripe/customers.parquet` | ~250 | IDs like `cus_XXXXX`, amounts in cents |
| `stripe/subscriptions.parquet` | ~175 | 70% of customers have subscriptions |
| `stripe/charges.parquet` | ~500 | Linked to customers |
| `stripe/invoices.parquet` | ~400 | Linked to subscriptions |
| `hubspot/contacts.parquet` | ~250 | Numeric IDs, amounts in dollars |
| `hubspot/companies.parquet` | ~20 | Realistic company names |
| `hubspot/deals.parquet` | ~100 | Linked to contacts and companies |

Key characteristics:

- Deterministic (Faker seed=42) for reproducible tests
- ~80% email overlap between Stripe and HubSpot
- ~10% Stripe-only, ~10% HubSpot-only records
- Realistic distributions: 5% delinquent customers, various deal stages

## Loading sample data

```bash
dinobase init
dinobase add parquet --path sample_data/ --name demo
dinobase query "SELECT COUNT(*) FROM demo.customers" --pretty
```

Or for split schemas matching production layout:

```bash
dinobase add parquet --path sample_data/stripe/ --name stripe
dinobase add parquet --path sample_data/hubspot/ --name hubspot
dinobase query "
  SELECT s.email, h.company
  FROM stripe.customers s
  JOIN hubspot.contacts h ON s.email = h.email
  LIMIT 5
" --pretty
```

## Project structure

```
dinobase/
  dinobase/          # Main package
  tests/                 # Test suite
  scripts/               # Data generation scripts
  sample_data/           # Generated test data (parquet)
  docs/                  # Documentation site (Starlight)
  pyproject.toml         # Package config
```

## Adding a new source

The preferred way to add sources is via YAML files in `dinobase/sync/sources/configs/`. No Python code needed.

### YAML REST API source

Create a new file like `dinobase/sync/sources/configs/myservice.yaml`:

```yaml
name: myservice
description: "MyService (things, stuff)"
type: rest
credentials:
  - name: api_key
    flag: --api-key
    env: MYSERVICE_API_KEY
    prompt: "MyService API key"
client:
  base_url: https://api.myservice.com/v1
  auth:
    type: bearer_token
    token: "{api_key}"
  paginator:
    type: json_link
    next_url_path: "response.next"
resources:
  - name: things
    endpoint:
      path: things
      data_selector: data
  - name: stuff
    endpoint:
      path: stuff
      data_selector: data
```

### YAML GraphQL source

```yaml
name: myservice
description: "MyService (things, stuff)"
type: graphql
credentials:
  - name: api_key
    flag: --api-key
    env: MYSERVICE_API_KEY
    prompt: "MyService API key"
endpoint: https://api.myservice.com/graphql
auth_prefix: "Bearer "
resources:
  - name: things
    query: "query($cursor: String) { things(first: 50, after: $cursor) { nodes { id name } pageInfo { hasNextPage endCursor } } }"
    data_path: things.nodes
    pagination:
      type: relay_cursor
      page_info_path: things.pageInfo
```

### Python registry entry

For dlt verified sources, add an entry in `dinobase/sync/registry.py`:

```python
_register(SourceEntry(
    name="myservice",
    import_path="sources.myservice.myservice_source",
    description="MyService (things, stuff)",
    credentials=[
        CredentialParam("api_key", "--api-key", "MYSERVICE_API_KEY", "MyService API key"),
    ],
))
```

dlt handles auth, pagination, and rate limiting automatically.

## Docs site

The docs use [Starlight](https://starlight.astro.build/) (Astro).

```bash
cd docs
npm install
npm run dev    # dev server at localhost:4321
npm run build  # production build
```

## Releasing to PyPI

The `dinobase` package is published to PyPI via GitHub Actions using [OIDC trusted publishing](https://docs.pypi.org/trusted-publishers/) — no API tokens required.

### How it works

- **CI** (`.github/workflows/ci.yml`) runs `pytest` on Python 3.10–3.12 for every push and pull request.
- **Release** (`.github/workflows/release.yml`) triggers on any `v*` tag, builds an sdist + wheel, and publishes to PyPI.

The version is defined once in `pyproject.toml`. `dinobase/__init__.py` reads it at runtime via `importlib.metadata`.

### Cutting a release

```bash
make bump V=0.2.0
git push origin main v0.2.0
```

`make bump V=x.y.z` updates `pyproject.toml`, commits, and creates the tag locally. The `git push` triggers the release workflow.
