---
title: Customizing a connector sync
description: Limit which resources sync, and pass extra arguments (like start_date) to a dlt verified source.
---

By default a connector syncs every resource the underlying [dlt verified source](https://github.com/dlt-hub/verified-sources) exposes, with the source's own default arguments. Two optional fields on a connector let you narrow that down.

## `resources` — pick which resources to sync

For connectors with many endpoints (Salesforce, Freshdesk, HubSpot, …) you often only need a handful. Pass a comma-separated list at `dinobase add` time:

```bash
dinobase add freshdesk --api-key $FD_KEY --domain mycompany \
    --resources tickets,agents,groups,ticket_fields
```

That writes the list to `~/.dinobase/config.yaml`:

```yaml
connectors:
  freshdesk:
    type: freshdesk
    credentials:
      api_secret_key: "..."
      domain: "mycompany"
    resources: [tickets, agents, groups, ticket_fields]
```

For an existing connector you can either edit the YAML by hand or override on a single sync:

```bash
dinobase sync freshdesk --resources tickets,agents
```

(`--resources` on `sync` is per-run; it doesn't update the saved config.)

## `params` — extra kwargs for the source factory

Some dlt verified sources accept arguments that dinobase doesn't surface as named CLI flags — for example, Freshdesk's `start_date` for time-bounded incremental sync. Use `--param KEY=VALUE` (repeatable) to forward them:

```bash
dinobase add freshdesk --api-key $FD_KEY --domain mycompany \
    --resources tickets \
    --param start_date=2026-03-20T00:00:00Z
```

Saved as:

```yaml
connectors:
  freshdesk:
    type: freshdesk
    credentials:
      api_secret_key: "..."
      domain: "mycompany"
    resources: [tickets]
    params:
      start_date: "2026-03-20T00:00:00Z"
```

The values are passed verbatim to the source factory function as `**kwargs`. Refer to the [dlt-hub/verified-sources](https://github.com/dlt-hub/verified-sources) repo for the per-source argument list.

### Notes & limits

- `params` only applies to dlt **verified-source** connectors (the default for most SaaS APIs). Connectors backed by a YAML REST config (`configs/<name>.yaml` in this repo — Intercom, HelpScout, Front, …) ignore `--param`; edit the YAML directly to change their behaviour.
- A `--param` whose key matches a credential field name (e.g. `--param api_key=…`) is rejected — credentials always win, so user params can't accidentally clobber auth.
- Both fields are local-only. Cloud-managed connectors ignore `--resources` and `--param` at `add` time.
