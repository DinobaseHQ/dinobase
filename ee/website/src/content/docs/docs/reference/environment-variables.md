---
title: Environment Variables
description: All environment variables recognized by Dinobase.
---

## Dinobase configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DINOBASE_DIR` | `~/.dinobase` | Override the Dinobase data directory |
| `DINOBASE_STORAGE_URL` | *(none)* | Cloud storage URL for data (e.g., `s3://bucket/dinobase/`). Enables cloud mode. |
| `ANTHROPIC_API_KEY` | *(none)* | Anthropic API key. When set, Dinobase runs a Claude agent after each sync to build the semantic layer (table descriptions, PII flags, relationship docs). |
| `DINOBASE_AUTO_ANNOTATE` | `true` | Set to `false` to disable automatic semantic layer building after sync. |

## Cloud storage credentials

Set these when using `--storage` or `DINOBASE_STORAGE_URL` for cloud-backed storage.

### Amazon S3

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key |
| `AWS_REGION` or `AWS_DEFAULT_REGION` | S3 region (e.g., `us-east-1`) |
| `S3_ENDPOINT` | Custom S3 endpoint for MinIO, Cloudflare R2, etc. |

### Google Cloud Storage

| Variable | Description |
|----------|-------------|
| `GCS_HMAC_KEY_ID` | GCS HMAC access key (create in Console > Settings > Interoperability) |
| `GCS_HMAC_SECRET` | GCS HMAC secret key |

### Azure Blob Storage

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Full Azure connection string (preferred) |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure storage account name (alternative) |
| `AZURE_STORAGE_ACCOUNT_KEY` | Azure storage account key (alternative) |

## Source credentials

Dinobase checks these environment variables when adding sources. Set them to avoid passing credentials on the command line.

### SaaS APIs

| Variable | Source |
|----------|--------|
| `STRIPE_SECRET_KEY` | Stripe |
| `HUBSPOT_API_KEY` | HubSpot |
| `PIPEDRIVE_API_KEY` | Pipedrive |
| `SALESFORCE_USERNAME` | Salesforce |
| `SALESFORCE_PASSWORD` | Salesforce |
| `SALESFORCE_SECURITY_TOKEN` | Salesforce |
| `GITHUB_TOKEN` | GitHub |
| `GITLAB_TOKEN` | GitLab |
| `JIRA_SUBDOMAIN` | Jira |
| `JIRA_EMAIL` | Jira |
| `JIRA_API_TOKEN` | Jira |
| `SLACK_TOKEN` | Slack |
| `ZENDESK_TOKEN` | Zendesk |
| `SHOPIFY_API_KEY` | Shopify |
| `SHOPIFY_SHOP_URL` | Shopify |
| `NOTION_API_KEY` | Notion |
| `AIRTABLE_TOKEN` | Airtable |
| `GOOGLE_APPLICATION_CREDENTIALS` | Google Sheets, Analytics, Ads, GCS |
| `GA_PROPERTY_ID` | Google Analytics |
| `FACEBOOK_ACCESS_TOKEN` | Facebook Ads |
| `FACEBOOK_ACCOUNT_ID` | Facebook Ads |
| `FRESHDESK_API_KEY` | Freshdesk |
| `FRESHDESK_DOMAIN` | Freshdesk |
| `INTERCOM_TOKEN` | Intercom |
| `DISCORD_TOKEN` | Discord |
| `TWILIO_ACCOUNT_SID` | Twilio |
| `TWILIO_AUTH_TOKEN` | Twilio |
| `SENDGRID_API_KEY` | SendGrid |
| `MAILCHIMP_API_KEY` | Mailchimp |
| `FRONT_TOKEN` | Front |
| `CLOSE_API_KEY` | Close |
| `COPPER_API_KEY` | Copper |
| `ATTIO_API_KEY` | Attio |
| `PADDLE_API_KEY` | Paddle |
| `CHARGEBEE_API_KEY` | Chargebee |
| `CHARGEBEE_SITE` | Chargebee |
| `RECURLY_API_KEY` | Recurly |
| `LEMONSQUEEZY_API_KEY` | Lemon Squeezy |
| `LINEAR_API_KEY` | Linear |
| `SENTRY_TOKEN` | Sentry |
| `PAGERDUTY_TOKEN` | PagerDuty |
| `OPSGENIE_API_KEY` | Opsgenie |
| `STATUSPAGE_API_KEY` | Statuspage |
| `MATOMO_TOKEN` | Matomo |
| `MATOMO_URL` | Matomo |
| `BING_WEBMASTER_API_KEY` | Bing Webmaster |
| `ASANA_TOKEN` | Asana |
| `STRAPI_API_KEY` | Strapi |
| `STRAPI_DOMAIN` | Strapi |
| `MUX_ACCESS_TOKEN` | Mux |
| `MUX_SECRET_KEY` | Mux |
| `PERSONIO_CLIENT_ID` | Personio |
| `PERSONIO_CLIENT_SECRET` | Personio |
| `WORKABLE_TOKEN` | Workable |
| `WORKABLE_SUBDOMAIN` | Workable |
| `BITBUCKET_USERNAME` | Bitbucket |
| `BITBUCKET_APP_PASSWORD` | Bitbucket |
| `GITLAB_TOKEN` | GitLab |
| `POSTHOG_API_KEY` | PostHog |
| `POSTHOG_PROJECT_ID` | PostHog |
| `MIXPANEL_API_SECRET` | Mixpanel |
| `SEGMENT_TOKEN` | Segment |
| `PLAUSIBLE_API_KEY` | Plausible |
| `HUBSPOT_MARKETING_API_KEY` | HubSpot Marketing |
| `CUSTOMERIO_API_KEY` | Customer.io |
| `HELPSCOUT_API_KEY` | HelpScout |
| `VITALLY_API_KEY` | Vitally |
| `GAINSIGHT_API_KEY` | Gainsight |
| `CLICKUP_API_KEY` | ClickUp |
| `MONDAY_API_KEY` | Monday |
| `TRELLO_API_KEY` | Trello |
| `TRELLO_TOKEN` | Trello |
| `TODOIST_API_KEY` | Todoist |
| `SHOPIFY_API_KEY` | Shopify |
| `SHOPIFY_SHOP_URL` | Shopify |
| `WOOCOMMERCE_CONSUMER_KEY` | WooCommerce |
| `WOOCOMMERCE_CONSUMER_SECRET` | WooCommerce |
| `WOOCOMMERCE_URL` | WooCommerce |
| `BIGCOMMERCE_ACCESS_TOKEN` | BigCommerce |
| `BIGCOMMERCE_STORE_HASH` | BigCommerce |
| `SQUARE_ACCESS_TOKEN` | Square |
| `BAMBOOHR_API_KEY` | BambooHR |
| `BAMBOOHR_SUBDOMAIN` | BambooHR |
| `GREENHOUSE_API_KEY` | Greenhouse |
| `LEVER_API_KEY` | Lever |
| `GUSTO_TOKEN` | Gusto |
| `DEEL_API_KEY` | Deel |
| `QUICKBOOKS_ACCESS_TOKEN` | QuickBooks |
| `XERO_ACCESS_TOKEN` | Xero |
| `BREX_API_KEY` | Brex |
| `MERCURY_API_KEY` | Mercury |
| `DATADOG_API_KEY` | Datadog |
| `DATADOG_APP_KEY` | Datadog |
| `NEWRELIC_API_KEY` | New Relic |
| `CLOUDFLARE_API_KEY` | Cloudflare |
| `VERCEL_TOKEN` | Vercel |
| `NETLIFY_TOKEN` | Netlify |
| `CONTENTFUL_ACCESS_TOKEN` | Contentful |
| `CONTENTFUL_SPACE_ID` | Contentful |
| `SANITY_TOKEN` | Sanity |
| `SANITY_PROJECT_ID` | Sanity |
| `WORDPRESS_URL` | WordPress |
| `WORDPRESS_USERNAME` | WordPress |
| `WORDPRESS_APP_PASSWORD` | WordPress |
| `FIGMA_TOKEN` | Figma |

### Databases

| Variable | Source |
|----------|--------|
| `DATABASE_URL` | All database sources (PostgreSQL, MySQL, etc.) |

### Cloud storage

| Variable | Source |
|----------|--------|
| `S3_BUCKET_URL` | Amazon S3 |
| `AWS_ACCESS_KEY_ID` | Amazon S3, Kinesis |
| `AWS_SECRET_ACCESS_KEY` | Amazon S3, Kinesis |
| `GCS_BUCKET_URL` | Google Cloud Storage |
| `AZURE_STORAGE_URL` | Azure Blob |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure Blob |
| `AZURE_STORAGE_ACCOUNT_KEY` | Azure Blob |
| `SFTP_URL` | SFTP |
| `SFTP_USERNAME` | SFTP |
| `SFTP_PASSWORD` | SFTP |

### Data streams

| Variable | Source |
|----------|--------|
| `MONGODB_URL` | MongoDB |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka |
| `KINESIS_STREAM_NAME` | Kinesis |
