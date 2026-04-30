---
title: SaaS API Connectors
description: Connect Stripe, HubSpot, Salesforce, Linear, and 60+ other SaaS tools to Dinobase.
---

SaaS connectors connect to cloud services via API keys or OAuth tokens. Data is synced using [dlt](https://dlthub.com/) verified sources, REST API connectors, and GraphQL connectors.

## CRM & Sales

### <img src="/logos/hubspot.svg" class="connector-logo" alt="" />HubSpot

Contacts, companies, deals, tickets.

```bash
dinobase add hubspot --api-key pat-na1-...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `HUBSPOT_API_KEY` | HubSpot private app token |

**Metadata:** Descriptions, enum options, and custom properties via the HubSpot Properties API.

### <img src="/logos/hubspot_marketing.svg" class="connector-logo" alt="" />HubSpot Marketing

Marketing contacts, companies, deals (via REST API connector).

```bash
dinobase add hubspot_marketing --api-key pat-na1-...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `HUBSPOT_MARKETING_API_KEY` |

### <img src="/logos/salesforce.svg" class="connector-logo" alt="" />Salesforce

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

### <img src="/logos/close.svg" class="connector-logo" alt="" />Close

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

### <img src="/logos/stripe.svg" class="connector-logo" alt="" />Stripe

Customers, subscriptions, charges, invoices.

```bash
dinobase add stripe --api-key sk_live_...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `STRIPE_SECRET_KEY` | Stripe secret key |

**Metadata:** Full field descriptions, types, enums, and `unix-time` format hints from Stripe's OpenAPI spec.

### <img src="/logos/paddle.svg" class="connector-logo" alt="" />Paddle

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

### <img src="/logos/lemon_squeezy.svg" class="connector-logo" alt="" />Lemon Squeezy

Products, orders, subscriptions.

```bash
dinobase add lemon_squeezy --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `LEMONSQUEEZY_API_KEY` |

---

## Developer Tools

### <img src="/logos/github.svg" class="connector-logo" alt="" />GitHub

Repos, issues, PRs, reactions, stargazers.

```bash
dinobase add github --token ghp_...
```

| Option | Env var |
|--------|---------|
| `--token` | `GITHUB_TOKEN` |

### <img src="/logos/gitlab.svg" class="connector-logo" alt="" />GitLab

Projects, issues, merge requests.

```bash
dinobase add gitlab --token glpat-...
```

| Option | Env var |
|--------|---------|
| `--token` | `GITLAB_TOKEN` |

### <img src="/logos/jira.svg" class="connector-logo" alt="" />Jira

Issues, projects, users.

```bash
dinobase add jira --subdomain mycompany --email user@example.com --api-token ...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--subdomain` | `JIRA_SUBDOMAIN` | Jira subdomain |
| `--email` | `JIRA_EMAIL` | Account email |
| `--api-token` | `JIRA_API_TOKEN` | API token |

### <img src="/logos/bitbucket.svg" class="connector-logo" alt="" />Bitbucket

Repositories, pull requests.

```bash
dinobase add bitbucket --username user --app-password ...
```

| Option | Env var |
|--------|---------|
| `--username` | `BITBUCKET_USERNAME` |
| `--app-password` | `BITBUCKET_APP_PASSWORD` |

### <img src="/logos/sentry.svg" class="connector-logo" alt="" />Sentry

Issues, events, projects.

```bash
dinobase add sentry --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SENTRY_TOKEN` |

### <img src="/logos/linear.svg" class="connector-logo" alt="" />Linear

Issues, projects, teams, users, labels, cycles, comments. Uses GraphQL with Relay pagination.

```bash
dinobase add linear --api-key lin_api_...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `LINEAR_API_KEY` |

---

## Infrastructure & Monitoring

### <img src="/logos/pagerduty.svg" class="connector-logo" alt="" />PagerDuty

Incidents, services, users.

```bash
dinobase add pagerduty --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `PAGERDUTY_TOKEN` |

### <img src="/logos/opsgenie.svg" class="connector-logo" alt="" />OpsGenie

Alerts, incidents, users.

```bash
dinobase add opsgenie --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `OPSGENIE_API_KEY` |

### <img src="/logos/statuspage.svg" class="connector-logo" alt="" />Statuspage

Pages, incidents, components.

```bash
dinobase add statuspage --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `STATUSPAGE_API_KEY` |

### <img src="/logos/datadog.svg" class="connector-logo" alt="" />Datadog

Monitors, dashboards, logs.

```bash
dinobase add datadog --api-key ... --app-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `DATADOG_API_KEY` |
| `--app-key` | `DATADOG_APP_KEY` |

### <img src="/logos/newrelic.svg" class="connector-logo" alt="" />New Relic

Applications, deployments, alerts.

```bash
dinobase add newrelic --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `NEWRELIC_API_KEY` |

### <img src="/logos/cloudflare.svg" class="connector-logo" alt="" />Cloudflare

Zones, DNS records, analytics.

```bash
dinobase add cloudflare --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `CLOUDFLARE_API_KEY` |

### <img src="/logos/vercel.svg" class="connector-logo" alt="" />Vercel

Projects, deployments, domains.

```bash
dinobase add vercel --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `VERCEL_TOKEN` |

### <img src="/logos/netlify.svg" class="connector-logo" alt="" />Netlify

Sites, deploys, forms.

```bash
dinobase add netlify --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `NETLIFY_TOKEN` |

---

## Communication

### <img src="/logos/slack.svg" class="connector-logo" alt="" />Slack

Channels, messages, users.

```bash
dinobase add slack --token xoxb-...
```

| Option | Env var |
|--------|---------|
| `--token` | `SLACK_TOKEN` |

### <img src="/logos/discord.svg" class="connector-logo" alt="" />Discord

Guilds, channels, messages.

```bash
dinobase add discord --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `DISCORD_TOKEN` |

### <img src="/logos/twilio.svg" class="connector-logo" alt="" />Twilio

Messages, calls, accounts.

```bash
dinobase add twilio --account-sid AC... --auth-token ...
```

| Option | Env var |
|--------|---------|
| `--account-sid` | `TWILIO_ACCOUNT_SID` |
| `--auth-token` | `TWILIO_AUTH_TOKEN` |

### <img src="/logos/sendgrid.svg" class="connector-logo" alt="" />SendGrid

Contacts, campaigns, stats.

```bash
dinobase add sendgrid --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SENDGRID_API_KEY` |

### <img src="/logos/mailchimp.svg" class="connector-logo" alt="" />Mailchimp

Lists, campaigns, members.

```bash
dinobase add mailchimp --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `MAILCHIMP_API_KEY` |

### Front

Conversations, contacts, inboxes.

```bash
dinobase add front --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `FRONT_TOKEN` |

---

## Support & Success

### <img src="/logos/zendesk.svg" class="connector-logo" alt="" />Zendesk

Tickets, users, organizations.

```bash
dinobase add zendesk --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `ZENDESK_TOKEN` |

### <img src="/logos/intercom.svg" class="connector-logo" alt="" />Intercom

Contacts, conversations, companies.

```bash
dinobase add intercom --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `INTERCOM_TOKEN` |

### Freshdesk

Tickets, contacts, companies, agents, groups.

```bash
dinobase add freshdesk --api-key ... --domain mycompany
```

| Option | Env var |
|--------|---------|
| `--api-key` | `FRESHDESK_API_KEY` |
| `--domain` | `FRESHDESK_DOMAIN` |

To limit which resources sync or to set a `start_date` for incremental tickets, see [Customizing a sync](/docs/connectors/customizing/).

### <img src="/logos/helpscout.svg" class="connector-logo" alt="" />HelpScout

Conversations, customers, mailboxes.

```bash
dinobase add helpscout --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `HELPSCOUT_API_KEY` |

### <img src="/logos/customerio.svg" class="connector-logo" alt="" />Customer.io

Customers, segments, campaigns.

```bash
dinobase add customerio --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `CUSTOMERIO_API_KEY` |

### Vitally

Accounts, users, health scores.

```bash
dinobase add vitally --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `VITALLY_API_KEY` |

### <img src="/logos/gainsight.svg" class="connector-logo" alt="" />Gainsight

Companies, relationships, CTAs.

```bash
dinobase add gainsight --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `GAINSIGHT_API_KEY` |

---

## E-commerce

### <img src="/logos/shopify.svg" class="connector-logo" alt="" />Shopify

Orders, products, customers.

```bash
dinobase add shopify --api-key shppa_... --shop-url myshop.myshopify.com
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--api-key` | `SHOPIFY_API_KEY` | Private app password |
| `--shop-url` | `SHOPIFY_SHOP_URL` | Shop URL |

### <img src="/logos/woocommerce.svg" class="connector-logo" alt="" />WooCommerce

Orders, products, customers.

```bash
dinobase add woocommerce --consumer-key ... --consumer-secret ... --url https://mystore.com
```

| Option | Env var |
|--------|---------|
| `--consumer-key` | `WOOCOMMERCE_CONSUMER_KEY` |
| `--consumer-secret` | `WOOCOMMERCE_CONSUMER_SECRET` |
| `--url` | `WOOCOMMERCE_URL` |

### <img src="/logos/bigcommerce.svg" class="connector-logo" alt="" />BigCommerce

Orders, products, customers.

```bash
dinobase add bigcommerce --access-token ... --store-hash ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `BIGCOMMERCE_ACCESS_TOKEN` |
| `--store-hash` | `BIGCOMMERCE_STORE_HASH` |

### <img src="/logos/square.svg" class="connector-logo" alt="" />Square

Payments, orders, customers.

```bash
dinobase add square --access-token ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `SQUARE_ACCESS_TOKEN` |

---

## Project Management

### <img src="/logos/asana.svg" class="connector-logo" alt="" />Asana

Workspaces, projects, tasks.

```bash
dinobase add asana --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `ASANA_TOKEN` |

Requires: `pip install asana`

### <img src="/logos/clickup.svg" class="connector-logo" alt="" />ClickUp

Spaces, lists, tasks.

```bash
dinobase add clickup --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `CLICKUP_API_KEY` |

### Monday

Boards, items, updates.

```bash
dinobase add monday --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `MONDAY_API_KEY` |

### <img src="/logos/trello.svg" class="connector-logo" alt="" />Trello

Boards, lists, cards.

```bash
dinobase add trello --api-key ... --token ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `TRELLO_API_KEY` |
| `--token` | `TRELLO_TOKEN` |

### <img src="/logos/todoist.svg" class="connector-logo" alt="" />Todoist

Projects, tasks, comments.

```bash
dinobase add todoist --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `TODOIST_API_KEY` |

---

## Marketing & Analytics

### <img src="/logos/facebook_ads.svg" class="connector-logo" alt="" />Facebook Ads

Campaigns, ad sets, ads, insights.

```bash
dinobase add facebook_ads --token ... --account-id act_123
```

| Option | Env var |
|--------|---------|
| `--token` | `FACEBOOK_ACCESS_TOKEN` |
| `--account-id` | `FACEBOOK_ACCOUNT_ID` |

Requires: `pip install facebook_business`

### <img src="/logos/google_analytics.svg" class="connector-logo" alt="" />Google Analytics

Google Analytics 4 data.

```bash
dinobase add google_analytics --property-id 123456 --credentials-file ./sa.json
```

| Option | Env var |
|--------|---------|
| `--property-id` | `GA_PROPERTY_ID` |
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-analytics-data`

### <img src="/logos/google_ads.svg" class="connector-logo" alt="" />Google Ads

Campaigns, ad groups, ads, keywords.

```bash
dinobase add google_ads --credentials-file ./sa.json
```

| Option | Env var |
|--------|---------|
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-ads`

### <img src="/logos/mixpanel.svg" class="connector-logo" alt="" />Mixpanel

Events, funnels, retention.

```bash
dinobase add mixpanel --api-secret ...
```

| Option | Env var |
|--------|---------|
| `--api-secret` | `MIXPANEL_API_SECRET` |

### <img src="/logos/posthog.svg" class="connector-logo" alt="" />PostHog

Events, persons, feature flags, cohorts, insights.

```bash
dinobase add posthog --api-key ... --project-id ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `POSTHOG_API_KEY` |
| `--project-id` | `POSTHOG_PROJECT_ID` |

### <img src="/logos/segment.svg" class="connector-logo" alt="" />Segment

Sources, events, users.

```bash
dinobase add segment --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SEGMENT_TOKEN` |

### <img src="/logos/plausible.svg" class="connector-logo" alt="" />Plausible

Sites, stats, pages.

```bash
dinobase add plausible --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `PLAUSIBLE_API_KEY` |

### <img src="/logos/matomo.svg" class="connector-logo" alt="" />Matomo

Visits, reports.

```bash
dinobase add matomo --token ... --url https://matomo.example.com
```

| Option | Env var |
|--------|---------|
| `--token` | `MATOMO_TOKEN` |
| `--url` | `MATOMO_URL` |

### <img src="/logos/bing_webmaster.svg" class="connector-logo" alt="" />Bing Webmaster

Page stats, query stats.

```bash
dinobase add bing_webmaster --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `BING_WEBMASTER_API_KEY` |

---

## HR & Recruiting

### <img src="/logos/personio.svg" class="connector-logo" alt="" />Personio

Employees, absences, attendances.

```bash
dinobase add personio --client-id ... --client-secret ...
```

| Option | Env var |
|--------|---------|
| `--client-id` | `PERSONIO_CLIENT_ID` |
| `--client-secret` | `PERSONIO_CLIENT_SECRET` |

### <img src="/logos/bamboohr.svg" class="connector-logo" alt="" />BambooHR

Employees, time off, reports.

```bash
dinobase add bamboohr --api-key ... --subdomain mycompany
```

| Option | Env var |
|--------|---------|
| `--api-key` | `BAMBOOHR_API_KEY` |
| `--subdomain` | `BAMBOOHR_SUBDOMAIN` |

### <img src="/logos/greenhouse.svg" class="connector-logo" alt="" />Greenhouse

Jobs, candidates, applications.

```bash
dinobase add greenhouse --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `GREENHOUSE_API_KEY` |

### Lever

Postings, opportunities, candidates.

```bash
dinobase add lever --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `LEVER_API_KEY` |

### <img src="/logos/workable.svg" class="connector-logo" alt="" />Workable

Jobs, candidates, activities.

```bash
dinobase add workable --token ... --subdomain mycompany
```

| Option | Env var |
|--------|---------|
| `--token` | `WORKABLE_TOKEN` |
| `--subdomain` | `WORKABLE_SUBDOMAIN` |

### <img src="/logos/gusto.svg" class="connector-logo" alt="" />Gusto

Employees, payrolls, companies.

```bash
dinobase add gusto --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `GUSTO_TOKEN` |

### Deel

Contracts, invoices, people.

```bash
dinobase add deel --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `DEEL_API_KEY` |

---

## Finance

### <img src="/logos/quickbooks.svg" class="connector-logo" alt="" />QuickBooks

Invoices, customers, accounts.

```bash
dinobase add quickbooks --access-token ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `QUICKBOOKS_ACCESS_TOKEN` |

### <img src="/logos/xero.svg" class="connector-logo" alt="" />Xero

Invoices, contacts, accounts.

```bash
dinobase add xero --access-token ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `XERO_ACCESS_TOKEN` |

### <img src="/logos/brex.svg" class="connector-logo" alt="" />Brex

Transactions, accounts, cards.

```bash
dinobase add brex --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `BREX_API_KEY` |

### <img src="/logos/mercury.svg" class="connector-logo" alt="" />Mercury

Transactions, accounts.

```bash
dinobase add mercury --api-key ...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `MERCURY_API_KEY` |

---

## Productivity

### <img src="/logos/notion.svg" class="connector-logo" alt="" />Notion

Notion databases.

```bash
dinobase add notion --api-key secret_...
```

| Option | Env var |
|--------|---------|
| `--api-key` | `NOTION_API_KEY` |

### <img src="/logos/airtable.svg" class="connector-logo" alt="" />Airtable

Bases and tables.

```bash
dinobase add airtable --token pat...
```

| Option | Env var |
|--------|---------|
| `--token` | `AIRTABLE_TOKEN` |

Requires: `pip install pyairtable`

### <img src="/logos/google_sheets.svg" class="connector-logo" alt="" />Google Sheets

```bash
dinobase add google_sheets --credentials-file ./service-account.json
```

| Option | Env var |
|--------|---------|
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` |

Requires: `pip install google-api-python-client`

---

## Content & CMS

### <img src="/logos/strapi.svg" class="connector-logo" alt="" />Strapi

Strapi CMS content.

```bash
dinobase add strapi --api-key ... --domain cms.example.com
```

| Option | Env var |
|--------|---------|
| `--api-key` | `STRAPI_API_KEY` |
| `--domain` | `STRAPI_DOMAIN` |

### <img src="/logos/contentful.svg" class="connector-logo" alt="" />Contentful

Entries, assets, content types.

```bash
dinobase add contentful --access-token ... --space-id ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `CONTENTFUL_ACCESS_TOKEN` |
| `--space-id` | `CONTENTFUL_SPACE_ID` |

### <img src="/logos/sanity.svg" class="connector-logo" alt="" />Sanity

Documents, assets.

```bash
dinobase add sanity --token ... --project-id ...
```

| Option | Env var |
|--------|---------|
| `--token` | `SANITY_TOKEN` |
| `--project-id` | `SANITY_PROJECT_ID` |

### <img src="/logos/wordpress.svg" class="connector-logo" alt="" />WordPress

Posts, pages, users.

```bash
dinobase add wordpress --url https://mysite.com --username ... --app-password ...
```

| Option | Env var |
|--------|---------|
| `--url` | `WORDPRESS_URL` |
| `--username` | `WORDPRESS_USERNAME` |
| `--app-password` | `WORDPRESS_APP_PASSWORD` |

---

## Design

### <img src="/logos/figma.svg" class="connector-logo" alt="" />Figma

Files, projects, comments.

```bash
dinobase add figma --token ...
```

| Option | Env var |
|--------|---------|
| `--token` | `FIGMA_TOKEN` |

---

## Video

### <img src="/logos/mux.svg" class="connector-logo" alt="" />Mux

Video assets, views.

```bash
dinobase add mux --access-token ... --secret-key ...
```

| Option | Env var |
|--------|---------|
| `--access-token` | `MUX_ACCESS_TOKEN` |
| `--secret-key` | `MUX_SECRET_KEY` |

---

## Data & Streaming

### <img src="/logos/mongodb.svg" class="connector-logo" alt="" />MongoDB

```bash
dinobase add mongodb --connection-string mongodb://...
```

| Option | Env var |
|--------|---------|
| `--connection-string` | `MONGODB_URL` |

Requires: `pip install pymongo`

### <img src="/logos/kafka.svg" class="connector-logo" alt="" />Kafka

```bash
dinobase add kafka --servers broker1:9092,broker2:9092
```

| Option | Env var |
|--------|---------|
| `--servers` | `KAFKA_BOOTSTRAP_SERVERS` |

Requires: `pip install confluent_kafka`

### <img src="/logos/kinesis.svg" class="connector-logo" alt="" />Kinesis

```bash
dinobase add kinesis --stream my-stream --access-key ... --secret-key ...
```

| Option | Env var |
|--------|---------|
| `--stream` | `KINESIS_STREAM_NAME` |
| `--access-key` | `AWS_ACCESS_KEY_ID` |
| `--secret-key` | `AWS_SECRET_ACCESS_KEY` |
