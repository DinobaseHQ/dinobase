---
title: SaaS API Sources
description: Connect Stripe, HubSpot, Salesforce, Shopify, and 20+ other SaaS tools to Dinobase.
---

SaaS sources connect to cloud services via API keys or OAuth tokens. Data is synced using [dlt](https://dlthub.com/) verified sources and REST API connectors.

## CRM & Sales

### HubSpot

Contacts, companies, deals, tickets.

```bash
dinobase add hubspot --api-key pat-na1-...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `HUBSPOT_API_KEY` | HubSpot private app token |

**Metadata:** Descriptions, enum options, and custom properties via the HubSpot Properties API.

### Salesforce

Full Salesforce CRM data.

```bash
dinobase add salesforce --username user@example.com --password pass --security-token TOKEN
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--username` | `SALESFORCE_USERNAME` | Salesforce username |
| `--password` | `SALESFORCE_PASSWORD` | Password |
| `--security-token` | `SALESFORCE_SECURITY_TOKEN` | Security token |

Requires: `pip install simple_salesforce`

### Pipedrive

Deals, persons, organizations, activities.

```bash
dinobase add pipedrive --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `PIPEDRIVE_API_KEY` |

### Close

Leads, contacts, opportunities.

```bash
dinobase add close --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `CLOSE_API_KEY` |

### Copper

Leads, people, companies.

```bash
dinobase add copper --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `COPPER_API_KEY` |

### Attio

Records, lists, notes.

```bash
dinobase add attio --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `ATTIO_API_KEY` |

---

## Payments & Billing

### Stripe

Customers, subscriptions, charges, invoices.

```bash
dinobase add stripe --api-key sk_live_...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `STRIPE_SECRET_KEY` | Stripe secret key |

**Metadata:** Full field descriptions, types, enums, and `unix-time` format hints from Stripe's OpenAPI spec.

### Paddle

Customers, subscriptions, transactions.

```bash
dinobase add paddle --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `PADDLE_API_KEY` |

### Chargebee

Customers, subscriptions, invoices.

```bash
dinobase add chargebee --api-key ... --site mysite
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `CHARGEBEE_API_KEY` | API key |
| `--site` | `CHARGEBEE_SITE` | Site name |

### Recurly

Accounts, subscriptions.

```bash
dinobase add recurly --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `RECURLY_API_KEY` |

### Lemon Squeezy

Products, orders, subscriptions.

```bash
dinobase add lemon_squeezy --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `LEMONSQUEEZY_API_KEY` |

---

## Developer Tools

### GitHub

Repos, issues, PRs, reactions, stargazers.

```bash
dinobase add github --token ghp_...
```

| Option | Env var |
|--------|---------|
| `--token` | `GITHUB_TOKEN` |

### GitLab

Projects, issues, merge requests.

```bash
dinobase add gitlab --token glpat-...
```

| Option | Env var |
|--------|---------|
| `--token` | `GITLAB_TOKEN` |

### Jira

Issues, projects, users.

```bash
dinobase add jira --subdomain mycompany --email user@example.com --api-token ...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--subdomain` | `JIRA_SUBDOMAIN` | Jira subdomain |
| `--email` | `JIRA_EMAIL` | Account email |
| `--api-token` | `JIRA_API_TOKEN` | API token |

### Bitbucket

Repositories, pull requests.

```bash
dinobase add bitbucket --username user --app-password ...
```

| Option | Env var |
|--------|---------|
| `--username` | `BITBUCKET_USERNAME` |
| `--app-password` | `BITBUCKET_APP_PASSWORD` |

### Sentry

Issues, events, projects.

```bash
dinobase add sentry --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SENTRY_TOKEN` |

### Linear

Issues, projects, teams.

```bash
dinobase add linear --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `LINEAR_API_KEY` |

### PagerDuty

Incidents, services, users.

```bash
dinobase add pagerduty --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `PAGERDUTY_TOKEN` |

### Opsgenie

Alerts, incidents, users.

```bash
dinobase add opsgenie --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `OPSGENIE_API_KEY` |

### Statuspage

Pages, incidents, components.

```bash
dinobase add statuspage --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `STATUSPAGE_API_KEY` |

---

## Communication

### Slack

Channels, messages, users.

```bash
dinobase add slack --token xoxb-...
```

| Option | Env var |
|--------|---------|
| `--token` | `SLACK_TOKEN` |

### Zendesk

Tickets, users, organizations.

```bash
dinobase add zendesk --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `ZENDESK_TOKEN` |

### Intercom

Contacts, conversations, companies.

```bash
dinobase add intercom --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `INTERCOM_TOKEN` |

### Discord

Guilds, channels, messages.

```bash
dinobase add discord --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `DISCORD_TOKEN` |

### Twilio

Messages, calls, accounts.

```bash
dinobase add twilio --account-sid AC... --auth-token ...
```

| Option | Env var |
|--------|---------|
| `--account-sid` | `TWILIO_ACCOUNT_SID` |
| `--auth-token` | `TWILIO_AUTH_TOKEN` |

### SendGrid

Contacts, campaigns, stats.

```bash
dinobase add sendgrid --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SENDGRID_API_KEY` |

### Front

Conversations, contacts, inboxes.

```bash
dinobase add front --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `FRONT_TOKEN` |

### Drift

Contacts, conversations.

```bash
dinobase add drift --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `DRIFT_TOKEN` |

---

## E-commerce

### Shopify

Orders, products, customers.

```bash
dinobase add shopify --api-key shppa_... --shop-url myshop.myshopify.com
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `SHOPIFY_API_KEY` | Private app password |
| `--shop-url` | `SHOPIFY_SHOP_URL` | Shop URL |

---

## Productivity

### Notion

Notion databases.

```bash
dinobase add notion --api-key secret_...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `NOTION_API_KEY` |

### Airtable

Bases and tables.

```bash
dinobase add airtable --token pat...
```

| Option | Env var |
|--------|---------|
| `--token` | `AIRTABLE_TOKEN` |

Requires: `pip install pyairtable`

### Google Sheets

```bash
dinobase add google_sheets --credentials-file ./service-account.json
```

| Option | Env var |
|--------|---------|
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-api-python-client`

### Asana

Workspaces, projects, tasks.

```bash
dinobase add asana --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `ASANA_TOKEN` |

Requires: `pip install asana`

---

## Marketing

### Facebook Ads

Campaigns, ad sets, ads, insights.

```bash
dinobase add facebook_ads --token ... --account-id act_123
```

| Option | Env var |
|--------|---------|
| `--token` | `FACEBOOK_ACCESS_TOKEN` |
| `--account-id` | `FACEBOOK_ACCOUNT_ID` |

Requires: `pip install facebook_business`

### Google Analytics

Google Analytics 4 data.

```bash
dinobase add google_analytics --property-id 123456 --credentials-file ./sa.json
```

| Option | Env var |
|--------|---------|
| `--property-id` | `GA_PROPERTY_ID` |
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-analytics-data`

### Google Ads

Campaigns, ad groups, ads, keywords.

```bash
dinobase add google_ads --credentials-file ./sa.json
```

| Option | Env var |
|--------|---------|
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-ads`

### Mailchimp

Lists, campaigns, members.

```bash
dinobase add mailchimp --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `MAILCHIMP_API_KEY` |

---

## Support

### Freshdesk

Tickets, contacts, companies.

```bash
dinobase add freshdesk --api-key ... --domain mycompany
```

| Option | Env var |
|--------|---------|
| `--api-key` | `FRESHDESK_API_KEY` |
| `--domain` | `FRESHDESK_DOMAIN` |

---

## Analytics

### Matomo

Visits, reports.

```bash
dinobase add matomo --token ... --url https://matomo.example.com
```

| Option | Env var |
|--------|---------|
| `--token` | `MATOMO_TOKEN` |
| `--url` | `MATOMO_URL` |

### Bing Webmaster

Page stats, query stats.

```bash
dinobase add bing_webmaster --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `BING_WEBMASTER_API_KEY` |

---

## Data

### MongoDB

```bash
dinobase add mongodb --connection-string mongodb://...
```

| Option | Env var |
|--------|---------|
| `--connection-string` | `MONGODB_URL` |

Requires: `pip install pymongo`

### Kafka

```bash
dinobase add kafka --servers broker1:9092,broker2:9092
```

| Option | Env var |
|--------|---------|
| `--servers` | `KAFKA_BOOTSTRAP_SERVERS` |

Requires: `pip install confluent_kafka`

### Kinesis

```bash
dinobase add kinesis --stream my-stream --access-key ... --secret-key ...
```

| Option | Env var |
|--------|---------|
| `--stream` | `KINESIS_STREAM_NAME` |
| `--access-key` | `AWS_ACCESS_KEY_ID` |
| `--secret-key` | `AWS_SECRET_ACCESS_KEY` |

---

## HR

### Personio

Employees, absences, attendances.

```bash
dinobase add personio --client-id ... --client-secret ...
```

| Option | Env var |
|--------|---------|
| `--client-id` | `PERSONIO_CLIENT_ID` |
| `--client-secret` | `PERSONIO_CLIENT_SECRET` |

### Workable

Jobs, candidates, activities.

```bash
dinobase add workable --token ... --subdomain mycompany
```

| Option | Env var |
|--------|---------|
| `--token` | `WORKABLE_TOKEN` |
| `--subdomain` | `WORKABLE_SUBDOMAIN` |

---

## Content

### Strapi

Strapi CMS content.

```bash
dinobase add strapi --api-key ... --domain cms.example.com
```

| Option | Env var |
|--------|---------|
| `--api-key` | `STRAPI_API_KEY` |
| `--domain` | `STRAPI_DOMAIN` |

---

## Video

### Mux

Video assets, views.

```bash
dinobase add mux --access-token ... --secret-key ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `MUX_ACCESS_TOKEN` |
| `--secret-key` | `MUX_SECRET_KEY` |
