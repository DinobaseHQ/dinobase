---
title: Development
description: Set up a development environment, run tests, and contribute to Dinobase.
---

## Setup

```bash
git clone https://github.com/dinobase/dinobase
cd dinobase
pip install -e ".[dev]"
```

Dev dependencies: `pytest`, `pytest-asyncio`.

## Running tests

```bash
pytest
```

Tests use sample parquet data loaded into an in-memory DuckDB instance.

### Test structure

```
tests/
  conftest.py           # Fixtures (sample_db with Stripe + HubSpot data)
  test_db.py            # DinobaseDB: metadata, sync logging, schema introspection
  test_query_engine.py  # QueryEngine: queries, joins, aggregations, describe
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
  src/dinobase/          # Main package
  tests/                 # Test suite
  scripts/               # Data generation scripts
  sample_data/           # Generated test data (parquet)
  docs/                  # Documentation site (Starlight)
  pyproject.toml         # Package config
```

## Adding a new source

To add a new SaaS source, add an entry to the registry in `src/dinobase/sync/registry.py`:

### dlt verified source

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

### REST API source

```python
_register_rest_api(
    "myservice",
    "MyService (things, stuff)",
    "https://api.myservice.com/v1/",
    "bearer", "token",
    env_var="MYSERVICE_API_KEY",
    prompt="MyService API key",
    resources=[
        {"name": "things", "endpoint": {"path": "things"}},
        {"name": "stuff", "endpoint": {"path": "stuff"}},
    ],
    data_selector="data",
)
```

No Python connector code needed -- dlt handles auth, pagination, and rate limiting.

## Docs site

The docs use [Starlight](https://starlight.astro.build/) (Astro).

```bash
cd docs
npm install
npm run dev    # dev server at localhost:4321
npm run build  # production build
```
