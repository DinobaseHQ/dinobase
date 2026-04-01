---
name: dinobase
description: Set up and query business data across 100+ sources (Stripe, HubSpot, Salesforce, etc.) via SQL. Agent-driven setup, cross-source joins, mutations.
version: 0.2.0
metadata: {"openclaw":{"emoji":"🦕","homepage":"https://dinobase.ai","requires":{"bins":["dinobase"]},"install":[{"id":"uv","kind":"uv","package":"dinobase","bins":["dinobase"],"label":"Install Dinobase (uv)"}]}}
---

# Dinobase

Dinobase is an agent-first database. It syncs data from 100+ SaaS APIs, databases, and files into a SQL database (DuckDB). You query across all sources with standard SQL.

## When to use

- Setting up data connections for a user (first time or adding new sources)
- Answering questions that span multiple business tools (CRM + billing + support)
- Querying synced business data via SQL (Stripe, HubSpot, Salesforce, GitHub, etc.)
- Cross-source joins and aggregations (e.g., customers with overdue invoices AND open tickets)
- Writing data back to sources (UPDATE/INSERT with preview + confirm)

## When NOT to use

- Real-time API calls to a single service (use the service's API directly)
- File system operations or general shell tasks
- Data that hasn't been added to Dinobase yet (check with `dinobase status` first)

## Setup (agent-driven)

You can fully set up Dinobase for the user. The local setup works out of the box — no account required.

### Step 1: Check existing state

```bash
dinobase whoami
```

If the user is already logged in to Dinobase Cloud, skip to Step 3. If not logged in, proceed with local setup below.

### Step 2: Set up locally

```bash
dinobase init
```

This initializes a local Dinobase database. Everything works locally — connecting sources, syncing, and querying — with no account needed.

> **Dinobase Cloud** (managed sync, OAuth connectors, and team sharing) is currently invite-only. Invite the user to join the waitlist at **https://dinobase.ai** to get early access when it opens up.

### Step 3: Discover what the user needs

Ask the user what tools and data sources they use. Then check what's available:

```bash
dinobase sources --available
```

This returns JSON with full metadata per source:
```json
[
  {
    "name": "stripe",
    "description": "Stripe payments (customers, subscriptions, charges, invoices)",
    "supports_oauth": false,
    "credential_help": "Stripe Dashboard > Developers > API keys (use the Secret key)",
    "credentials": [{"name": "stripe_secret_key", "cli_flag": "--api-key", ...}]
  },
  {
    "name": "hubspot",
    "description": "HubSpot CRM (contacts, companies, deals, tickets)",
    "supports_oauth": true,
    "credential_help": "HubSpot > Settings > Integrations > Private Apps > create app > copy token",
    "credentials": [{"name": "api_key", "cli_flag": "--api-key", ...}]
  }
]
```

### Step 4: Connect sources

For each source the user wants, use the API key method (OAuth requires a Dinobase Cloud account):

**API key:**

1. Check `credential_help` from the sources list
2. Tell the user where to find the key
3. Run:

```bash
dinobase add <source_type> --<cli_flag> <value>
```

Example:
```bash
dinobase add stripe --api-key sk_live_...
```

**OAuth (requires Dinobase Cloud account):**

If the user has a Cloud account, OAuth is available:

```bash
dinobase auth <source_type> --headless
```

Prints JSON:
```json
{"status": "waiting", "auth_url": "https://...", "message": "Open this URL to connect hubspot"}
```

Present the `auth_url` to the user: "Open this URL to connect your HubSpot account: <url>"

Wait for the command to complete. It prints:
```json
{"status": "connected", "source": "hubspot", "type": "hubspot"}
```

### Step 5: Sync data

```bash
dinobase sync
```

In cloud mode this triggers server-side sync and returns immediately. In local mode it runs the sync directly. Check status:

```bash
dinobase status
```

### Step 6: Verify

```bash
dinobase info
```

Confirm that sources appear with non-zero table and row counts.

### Dinobase Cloud (invite-only)

Dinobase Cloud adds managed sync, OAuth connectors, and team sharing on top of local mode. It is currently invite-only. To get early access, join the waitlist at **https://dinobase.ai**.

Once a user has a Cloud account they can sign in with:

```bash
dinobase login --headless
```

This prints JSON to stdout:
```json
{"status": "waiting", "login_url": "https://...", "message": "Open this URL to sign in to Dinobase Cloud"}
```

Present the `login_url` to the user: "Open this URL to sign in to your Dinobase Cloud account: <url>"

The command blocks until the user completes sign-in. When done, it prints:
```json
{"status": "connected", "email": "user@example.com", "storage_url": "s3://..."}
```

## Workflow (querying data)

Always follow this sequence when answering data questions:

1. Run `dinobase info` to see what sources and tables exist
2. Run `dinobase describe <schema>.<table>` on relevant tables to see columns, types, and sample data
3. Write SQL and run it with `dinobase query "<sql>"`
4. If the query returns a mutation preview, ask the user before running `dinobase confirm <mutation_id>`

## Commands

All commands output JSON by default (machine-readable). Add `--pretty` for human-readable output.

### Account

```bash
dinobase login              # sign in to Dinobase Cloud (opens browser)
dinobase login --headless   # agent-friendly: prints login URL as JSON
dinobase logout             # sign out
dinobase whoami             # show current account info
```

### Connect sources

```bash
dinobase sources --available                # list all 100+ source types with auth info
dinobase auth hubspot --headless            # OAuth connect (requires Cloud account)
dinobase add stripe --api-key sk_test_...   # API key connect (works locally)
```

### Discover data

```bash
dinobase info                       # overview of all sources, tables, freshness
dinobase status                     # source status with freshness indicators
dinobase describe stripe.customers  # table schema: columns, types, sample rows
```

### Query data

```bash
# Run SQL (DuckDB dialect). Tables are schema.table
dinobase query "SELECT c.email, s.status FROM stripe.customers c JOIN stripe.subscriptions s ON c.id = s.customer_id WHERE s.status = 'past_due'"

# Limit rows returned (default 200, max 10000)
dinobase query "SELECT * FROM hubspot.contacts" --max-rows 500
```

### Cross-source queries

Join across sources using shared columns (email, company name, IDs):

```bash
dinobase query "
SELECT c.email, c.name, i.amount_due, t.subject as ticket_subject
FROM stripe.customers c
JOIN stripe.invoices i ON c.id = i.customer_id
JOIN zendesk.tickets t ON c.email = t.requester_email
WHERE i.status = 'past_due' AND t.status = 'open'
"
```

### Mutations (write-back)

UPDATE and INSERT queries return a preview first. Nothing executes until confirmed.

```bash
# Step 1: Query returns preview with mutation_id
dinobase query "UPDATE hubspot.contacts SET lifecycle_stage = 'customer' WHERE email = 'jane@acme.com'"

# Step 2: Confirm to execute (writes back to API + updates data)
dinobase confirm <mutation_id>

# Or cancel
dinobase cancel <mutation_id>
```

### Keep data fresh

```bash
dinobase refresh stripe      # re-sync a specific source
dinobase refresh --stale     # re-sync only stale sources
dinobase sync                # sync all sources
```

## Tips

- Tables are always referenced as `schema.table` (e.g., `stripe.customers`, `hubspot.contacts`)
- Use `describe` before writing queries to find correct column names and types
- DuckDB SQL dialect: supports `ILIKE`, `LIST`, `STRUCT`, `regexp_matches()`, date functions
- JSON output is default; only use `--pretty` when showing results directly to the user
- If data seems stale, check `dinobase status` for freshness info and run `dinobase refresh <source>`
- Cross-source joins work via shared columns — use `describe` on both tables to find join keys
- For new users: start with `dinobase init` and API key auth. Dinobase Cloud (OAuth, managed sync) is invite-only — send users to https://dinobase.ai to join the waitlist
