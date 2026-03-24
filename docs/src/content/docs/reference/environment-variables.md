---
title: Environment Variables
description: All environment variables recognized by Dinobase.
---

## Dinobase configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DINOBASE_DIR` | `~/.dinobase` | Override the Dinobase data directory |

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
| `DRIFT_TOKEN` | Drift |
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
