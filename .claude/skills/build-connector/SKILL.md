---
name: build-connector
description: Build a new Dinobase YAML connector for a REST API that dlt doesn't have a verified source for. Researches the API, writes the YAML config with read + write endpoints, incremental loading, pagination, and auth.
argument-hint: <api_name>
---

# Build a Dinobase Connector

You are building a YAML connector config for Dinobase — an agent-first database that syncs data from 100+ sources into DuckDB.

**When to write a YAML connector vs use the registry:**
- If dlt has a verified source for this API (check `sources/` package), just add a registry entry in `dinobase/sync/registry.py`. No YAML needed.
- If dlt does NOT have a verified source, write a YAML config. The YAML is translated to dlt's `rest_api_source` which handles auth, pagination, rate limiting, and incremental loading.

The API name to build a connector for: $ARGUMENTS

## Step 1: Research the API

Before writing anything, research the API thoroughly. You need:

1. **Base URL** and API versioning
2. **Auth method** — bearer token, API key (header/query/body), HTTP basic, OAuth
3. **Pagination** — cursor, offset, link header, page number
4. **All read endpoints** — every resource the API exposes (list, get, search)
5. **All write endpoints** — create, update, delete, batch operations
6. **Data format** — where records live in the response JSON (e.g., `data`, `results`, `items`)
7. **Incremental fields** — `updated_at`, `modified_date`, `created` timestamps for change tracking
8. **Rate limits**
9. **Nested/child resources** — e.g., `/deals/{id}/activities`
10. **Bulk/batch endpoints** — for efficient writes

Use WebFetch and WebSearch to read the API documentation. Get the actual field names, endpoint paths, and response formats.

## Step 2: Check if dlt already has it

```bash
python3 -c "import sources; import pkgutil; [print(n) for _, n, _ in pkgutil.iter_modules(sources.__path__) if '<name>' in n.lower()]"
```

If dlt has it, add a registry entry instead (see `dinobase/sync/registry.py` for examples) and stop.

## Step 3: Write the YAML config

Save to `dinobase/sync/sources/configs/<api_name>.yaml`.

Follow this structure exactly:

```yaml
name: <api_name>
description: "<One-line description of the API and what data it provides>"

credentials:
  - name: <credential_name>        # internal name, used in {templates}
    flag: "--<cli-flag>"            # e.g. "--api-key"
    env: <ENV_VAR_NAME>             # e.g. EXAMPLE_API_KEY
    prompt: "<Interactive prompt>"  # shown when user runs `dinobase add`
    secret: true                    # hide input

client:
  base_url: https://api.example.com/v1/
  auth:
    type: bearer                    # bearer, http_basic, api_key
    token: "{api_key}"              # {credential_name} substitution
  paginator:
    type: cursor                    # cursor, json_link, offset, page_number, header_link
    cursor_path: meta.next_cursor   # JSON path to next page cursor
    cursor_param: cursor            # query param name for cursor

resource_defaults:
  primary_key: id
  write_disposition: merge          # merge, replace, or append
  endpoint:
    params:
      limit: 100
    data_selector: data             # JSON path to the array of records

resources:
  # One entry per API resource (becomes a table in Dinobase)
  - name: <table_name>
    endpoint:
      path: <api_path>
      data_selector: <json_path>    # override default if different
      params:
        updated_after: "{incremental.start_value}"  # inject cursor into API
    primary_key: id
    write_disposition: merge
    incremental:
      cursor_path: updated_at       # field in response to track
      initial_value: "2024-01-01T00:00:00Z"

  # Nested/child resource (depends on parent)
  - name: <child_table>
    endpoint:
      path: <parent>/{parent_id}/<child_path>
      data_selector: results
    parent:
      resource: <parent_table>      # name of the parent resource above
      field: id                     # parent field to use
      param: parent_id              # path parameter to substitute
    write_disposition: append

  # Large/expensive resources — excluded from default sync
  - name: audit_logs
    endpoint:
      path: audit-logs
    selected: false                 # user opts in with --resources

write_endpoints:
  # One entry per write operation (used by mutation engine for reverse ETL)
  - name: update_<resource>
    description: "Update a <resource>"
    method: PATCH                   # POST, PUT, PATCH, DELETE
    path: <resource>/{id}           # {id} substituted from mutation
    request_body_path: properties   # optional: nest body under this key

  - name: create_<resource>
    description: "Create a new <resource>"
    method: POST
    path: <resource>

  - name: batch_update_<resource>
    description: "Update multiple <resources>"
    method: POST
    path: <resource>/batch/update
    bulk: true
    max_batch_size: 100
```

### Auth types

| Type | Fields | Example |
|------|--------|---------|
| `bearer` | `token` | `Authorization: Bearer {token}` |
| `http_basic` | `username`, `password` | Stripe: key as username, empty password |
| `api_key` | `name`, `api_key`, `location` (header/query) | Pipedrive: `?api_token=` |

### Paginator types

| Type | Fields | Example API |
|------|--------|-------------|
| `cursor` | `cursor_path`, `cursor_param` | Stripe, HubSpot |
| `json_link` | `next_url_path` | APIs with next page URL in body |
| `header_link` | — | GitHub (Link header) |
| `offset` | `limit`, `offset_param`, `total_path` | Pipedrive |
| `page_number` | `page_param`, `total_path` | GitLab |

### Multiple auth methods

If the API uses different auth for different endpoint groups:

```yaml
auth_methods:
  dashboard:
    type: http_basic
    username: "{api_key}"
    password: "{secret_key}"
  ingestion:
    type: bearer
    token: "{api_key}"

resources:
  - name: events
    auth: dashboard         # use named auth method
  - name: ingest
    auth: ingestion
```

### Multiple base URLs

Override per-resource if the API has different hosts:

```yaml
resources:
  - name: ingest
    endpoint:
      base_url: https://ingest.example.com   # overrides client.base_url
      path: /batch
```

## Step 4: Add to the registry

Add an entry in `dinobase/sync/registry.py` so the CLI knows about it:

```python
_register(SourceEntry(
    name="<api_name>",
    import_path="dlt.sources.rest_api.rest_api_source",  # YAML sources use rest_api_source
    description="<description>",
    credentials=[
        CredentialParam("<name>", "<flag>", "<env>", "<prompt>"),
    ],
))
```

## Step 5: Test

```bash
dinobase add <api_name> --api-key <test_key>
dinobase sync <api_name>
dinobase describe <api_name>.<table>
dinobase query "SELECT * FROM <api_name>.<table> LIMIT 5"
```

## Rules

- **Map the API 1:1** — every list/get endpoint should be a resource, every create/update/delete should be a write_endpoint
- **Always add incremental** if the API supports filtering by updated_at or similar
- **Always add write_endpoints** — the mutation engine needs them for reverse ETL
- **Set `selected: false`** on large endpoints (audit logs, events) that would slow down default syncs
- **Use `{incremental.start_value}`** in params to pass the cursor to the API
- **Don't guess** — read the actual API docs for field names, pagination patterns, and auth
- **One YAML per source** — don't combine multiple APIs into one file
