# Dinobase EE (Enterprise Edition)

This directory contains Dinobase components licensed under the [Elastic License 2.0 (ELv2)](LICENSE), **not MIT**.

The core Dinobase project (everything outside `ee/`) remains MIT-licensed.

## What's here

### oauth-proxy

A standalone OAuth proxy server that handles OAuth authorization flows on behalf of the Dinobase CLI. It holds client credentials for each provider so users can connect sources with a single `dinobase auth <source>` command instead of manually creating API keys.

**Quick start:**

```bash
cd ee/oauth-proxy
pip install -e .

# Configure credentials for each provider
export DINOBASE_OAUTH_HUBSPOT_CLIENT_ID=...
export DINOBASE_OAUTH_HUBSPOT_CLIENT_SECRET=...

# Run the proxy
dinobase-oauth-proxy
```

See [ee/oauth-proxy/](oauth-proxy/) for full documentation.
