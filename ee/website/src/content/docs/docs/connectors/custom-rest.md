---
title: Custom REST Connectors
description: Connect any REST API to Dinobase by writing a local YAML config. Handles auth, pagination, and live or scheduled fetching.
---

Connect any REST API endpoint by creating a local YAML config. Data is fetched via dlt (handles auth, pagination) and cached as JSON files that DuckDB queries via `read_json_auto()`.

Use this when Dinobase doesn't ship a built-in connector for the service you need — any REST API with JSON responses works.

## Quick start

```bash
# Scaffold a connector
dinobase connector create posthog_flags \
  --url "https://app.posthog.com/api/" \
  --endpoint "projects/123/feature_flags/" \
  --data-selector results

# Add credentials
dinobase add posthog_flags --api-key phx_xxx

# Query (auto-fetches on first access in live mode)
dinobase query "SELECT name, active FROM posthog_flags.feature_flags"
```

## Connector YAML format

Configs live at `~/.dinobase/connectors/<name>.yaml` and use the same format as built-in connectors:

```yaml
name: posthog_flags
description: "PostHog feature flags"
mode: live  # live | sync | auto

credentials:
  - name: api_key
    flag: "--api-key"
    env: POSTHOG_API_KEY
    secret: true

client:
  base_url: "https://app.posthog.com/api/"
  auth:
    type: bearer
    token: "{api_key}"
  paginator:
    type: json_link
    next_url_path: "next"

resource_defaults:
  primary_key: id
  endpoint:
    data_selector: "results"

resources:
  - name: feature_flags
    endpoint:
      path: projects/12345/feature_flags/
```

## Authentication types

| Type | Description |
|------|-------------|
| `bearer` | `Authorization: Bearer {token}` header |
| `http_basic` | HTTP Basic auth with username/password |
| `api_key_header` | Custom header (e.g., `X-API-Key: {key}`) |

Set the `--auth-type` flag on `dinobase connector create` or edit the `client.auth.type` field in the YAML.

## Fetch modes

| Mode | Behavior |
|------|----------|
| `live` | Auto-fetches when queried and data is missing or stale |
| `sync` | Only fetches on `dinobase sync` or `dinobase refresh` |
| `auto` (default) | `live` if no paginator, `sync` if paginator is defined |

## Managing connectors

```bash
dinobase connector list --pretty    # List all local connectors
dinobase connector validate my_api  # Check YAML for errors
dinobase connector edit my_api      # Open in $EDITOR
dinobase refresh my_api             # Re-fetch data
```

## See also

- [Connectors guide](/docs/guides/connecting-sources/) — overview of all connector types
- [CLI reference for `connector create`](/docs/reference/cli/#dinobase-connector-create-name) — all flags
- [MCP server connectors](/docs/connectors/mcp/) — for MCP-based tools instead of REST APIs
