---
title: Self-Hosting on Hetzner
description: Run your own private Dinobase Cloud instance (API + web UI) on a single Hetzner Cloud VM using Docker Compose and Caddy for HTTPS.
---

This guide walks through deploying the full Dinobase cloud UI — API, sync/query workers, Next.js web frontend, and TLS — on a single [Hetzner Cloud](https://www.hetzner.com/cloud) VM. You end up with a private instance at `https://dinobase.<your-domain>` that only you (or your team) can log into.

If you just want a single-user CLI + MCP server instead of the full UI, see the main [Getting Started](/docs/getting-started/) — you can run `dinobase serve` directly on any VM without any of this.

## What you get

```
            Internet
                │
          Caddy (80/443)  ── Let's Encrypt
          ╱           ╲
      web:3000     api:8787 ──► query:8789 (in-proc DuckDB)
                       │
                   worker (sync loop)
                       │
                  /data volume  ◄── or Hetzner Object Storage (S3)
```

One VM runs five containers:

| Service | Purpose |
|---|---|
| `caddy` | TLS termination, HTTP → HTTPS redirect, reverse proxy |
| `web` | Next.js frontend (the UI you log into) |
| `api` | FastAPI server — auth, sources, connectors, proxies `/query` |
| `query` | In-process DuckDB query engine (separate container for isolation) |
| `worker` | Background sync loop that pulls data from source APIs |

All config lives in [`ee/cloud/deploy/hetzner/`](https://github.com/DinobaseHQ/dinobase/tree/main/ee/cloud/deploy/hetzner) in the repo.

## Prerequisites

1. **Hetzner Cloud account** with a project. [Sign up](https://accounts.hetzner.com/signUp) if you don't have one.
2. **A domain you control**, e.g. `chloris.co.il`. You'll create two subdomain `A` records later.
3. **A free [Supabase](https://supabase.com/) project** — Dinobase uses Supabase for user auth and metadata storage.

### Recommended VM size

| Workload | Hetzner type | Specs | ~cost/mo |
|---|---|---|---|
| Just you, a few sources | **CPX21** | 3 vCPU / 4 GB / 80 GB | ~€8 |
| Small team, 10+ sources | **CPX31** | 4 vCPU / 8 GB / 160 GB | ~€15 |
| Heavy sync / large data | **CPX41** | 8 vCPU / 16 GB / 240 GB | ~€29 |

Pick **Ubuntu 24.04** as the OS image and add your SSH key.

## Step 1 — Create the VM

In the Hetzner Cloud Console:

1. **Servers → Add Server**.
2. Location: pick the EU region closest to you (Falkenstein / Nuremberg / Helsinki).
3. Image: **Ubuntu 24.04**.
4. Type: **CPX21** (or larger per table above).
5. Networking: IPv4 + IPv6 (default).
6. SSH keys: add yours.
7. Name: `dinobase`.

Copy the public IPv4 address from the server detail page.

## Step 2 — DNS

At your domain registrar, add two `A` records pointing at the VM's IP. Using `chloris.co.il` as an example:

| Type | Name | Value |
|---|---|---|
| A | `dinobase` | `<vm-ip>` |
| A | `api.dinobase` | `<vm-ip>` |

Wait a minute, then verify from anywhere:

```bash
dig +short dinobase.chloris.co.il
dig +short api.dinobase.chloris.co.il
```

Both should return your VM's IP before you continue — Let's Encrypt validates via DNS + HTTP.

## Step 3 — Provision the VM

SSH in as `root` and run the install script:

```bash
ssh root@<vm-ip>
curl -fsSL https://raw.githubusercontent.com/DinobaseHQ/dinobase/main/ee/cloud/deploy/hetzner/install.sh | bash
```

This installs Docker + the compose plugin, opens the firewall (22/80/443), and clones the repo to `/opt/dinobase`.

## Step 4 — Set up Supabase

1. Create a project at [supabase.com](https://supabase.com/).
2. Wait ~1 min for it to provision, then go to **Project Settings → API** and copy:
   - `URL`
   - `publishable` key (starts with `sb_publishable_`)
   - `secret` key (starts with `sb_secret_`) — keep this private
3. Go to **Authentication → URL Configuration** and add your web domain to the redirect allowlist:
   - Site URL: `https://dinobase.chloris.co.il`
   - Redirect URLs: `https://dinobase.chloris.co.il/**`

## Step 5 — Configure

Back on the VM:

```bash
cd /opt/dinobase/ee/cloud/deploy/hetzner
cp .env.example .env
nano .env
```

Fill in at minimum:

```env
DINOBASE_WEB_DOMAIN=dinobase.chloris.co.il
DINOBASE_API_DOMAIN=api.dinobase.chloris.co.il
DINOBASE_ACME_EMAIL=you@chloris.co.il
DINOBASE_PUBLIC_WEB_URL=https://dinobase.chloris.co.il
DINOBASE_PUBLIC_API_URL=https://api.dinobase.chloris.co.il

DINOBASE_BASE_URL=https://api.dinobase.chloris.co.il
DINOBASE_ALLOWED_ORIGINS=https://dinobase.chloris.co.il

# Generate once, then paste:
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DINOBASE_ENCRYPTION_KEY=...

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
```

The encryption key is used to encrypt source credentials at rest. **Don't lose it** — you can't decrypt stored credentials without it.

## Step 6 — Launch

```bash
docker compose up -d --build
docker compose logs -f caddy
```

Watch for `certificate obtained successfully` — that means Let's Encrypt succeeded. First boot takes ~3–5 min because both images build from source.

Open `https://dinobase.chloris.co.il` in a browser. Sign up with your email — the first user becomes the owner.

## Storage: local volume vs. object storage

By default, synced data lives in the `dinobase-data` Docker volume on the VM. That's fine up to tens of GB. For larger data or if you want the VM to be disposable, switch to S3-compatible object storage — Hetzner offers [Object Storage](https://www.hetzner.com/storage/object-storage/) in all EU regions.

In `.env`, comment out the default volume mount (edit `docker-compose.yml`) and set:

```env
AWS_ACCESS_KEY_ID=<hetzner object storage access key>
AWS_SECRET_ACCESS_KEY=<hetzner object storage secret>
AWS_DEFAULT_REGION=fsn1
DINOBASE_STORAGE_BUCKET=dinobase
```

See [Cloud Storage Backend](/docs/guides/cloud-storage-backend/) for the full recipe (including the S3 endpoint override needed for non-AWS providers).

## Day-2 operations

```bash
# Tail logs
docker compose logs -f api

# Upgrade to the latest main
cd /opt/dinobase && git pull
cd ee/cloud/deploy/hetzner && docker compose up -d --build

# Stop everything (volumes preserved)
docker compose down

# Backup the data volume
docker run --rm \
  -v dinobase_dinobase-data:/data \
  -v $PWD:/backup \
  alpine tar czf /backup/dinobase-$(date +%F).tgz -C /data .
```

## Troubleshooting

**Caddy keeps retrying the ACME challenge.** DNS hasn't propagated yet or one of the A records is wrong. Re-check `dig +short` for both subdomains.

**Web shows "Network error" on login.** `NEXT_PUBLIC_API_URL` was wrong at build time. The web Dockerfile bakes `NEXT_PUBLIC_*` vars into the bundle, so after editing `.env` you must rebuild: `docker compose up -d --build web`.

**Supabase auth returns "Invalid redirect URL".** Add your exact web domain (with `/**` suffix) under Authentication → URL Configuration in the Supabase dashboard.

**Worker isn't picking up new sources.** Check `docker compose logs worker`. Most often it's a missing OAuth client id/secret for a source that requires OAuth.
