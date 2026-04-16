# Dinobase self-hosted on Hetzner

Single-VM Docker Compose deployment for the full Dinobase cloud UI (API, query + sync workers, Next.js web, Caddy for TLS).

> **Full guide with screenshots:** [Self-Hosting on Hetzner](../../../../website/src/content/docs/docs/guides/self-hosting-hetzner.md)

## Prerequisites

1. A Hetzner Cloud VM — **CPX21** or larger (3 vCPU / 4 GB RAM / 80 GB disk), Ubuntu 24.04.
2. A domain you control. Create two A records pointing at the VM's public IP:
   - `dinobase.<your-domain>` → web UI
   - `api.dinobase.<your-domain>` → API
3. A free [Supabase](https://supabase.com) project (used for auth + user metadata).

## 1. Provision the VM

SSH in as root and run:

```bash
curl -fsSL https://raw.githubusercontent.com/DinobaseHQ/dinobase/main/ee/cloud/deploy/hetzner/install.sh | bash
```

That installs Docker, opens the firewall (22/80/443), and clones the repo to `/opt/dinobase`.

## 2. Configure

```bash
cd /opt/dinobase/ee/cloud/deploy/hetzner
cp .env.example .env
nano .env
```

Required values:

| Var | How to get it |
|---|---|
| `DINOBASE_WEB_DOMAIN`, `DINOBASE_API_DOMAIN` | The two subdomains you set up in DNS |
| `DINOBASE_ACME_EMAIL` | Your email (for Let's Encrypt expiry notices) |
| `DINOBASE_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` | Supabase → Project Settings → API |

In the Supabase dashboard, go to **Authentication → URL Configuration** and add both domains to the redirect allowlist.

## 3. Launch

```bash
docker compose up -d --build
docker compose logs -f
```

First boot builds both images (~3–5 min). Once Caddy logs `certificate obtained`, browse to `https://dinobase.<your-domain>`.

## 4. Day-2 ops

```bash
docker compose ps                 # service status
docker compose logs -f api        # tail API logs
docker compose pull && \
  docker compose up -d --build    # upgrade to latest main
docker compose down               # stop everything (volumes preserved)
```

Data lives in the `dinobase_dinobase-data` Docker volume. Back it up with:

```bash
docker run --rm -v dinobase_dinobase-data:/data -v $PWD:/backup alpine \
  tar czf /backup/dinobase-$(date +%F).tgz -C /data .
```

## Architecture

```
            Internet
                |
          Caddy (80/443)
          /           \
      web:3000     api:8787 ──► query:8789 (in-proc DuckDB)
                       │
                   worker (sync loop)
                       │
                   /data volume  ◄── or Hetzner Object Storage (S3)
```

All three dinobase services share the image built from `ee/cloud/api/Dockerfile`; they only differ by `DINOBASE_MODE`.
