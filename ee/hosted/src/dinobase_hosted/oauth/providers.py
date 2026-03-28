# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""OAuth provider registry — maps provider names to their OAuth endpoints and scopes.

Each provider needs:
- authorization_url: Where users grant access
- token_url: Where we exchange codes for tokens
- scopes: What permissions to request
- Client ID and secret are read from env vars at runtime (see config.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    authorization_url: str
    token_url: str
    scopes: list[str] = field(default_factory=list)
    # Some providers need extra params on the authorize request
    extra_authorize_params: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[str, OAuthProvider] = {}


def _register(p: OAuthProvider) -> None:
    PROVIDERS[p.name] = p


# ---------------------------------------------------------------------------
# CRM & Sales
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="hubspot",
    authorization_url="https://app.hubspot.com/oauth/authorize",
    token_url="https://api.hubapi.com/oauth/v1/token",
    scopes=[
        "crm.objects.contacts.read", "crm.objects.companies.read",
        "crm.objects.deals.read", "crm.objects.owners.read",
        "content", "forms", "tickets",
    ],
))

_register(OAuthProvider(
    name="hubspot_marketing",
    authorization_url="https://app.hubspot.com/oauth/authorize",
    token_url="https://api.hubapi.com/oauth/v1/token",
    scopes=[
        "content", "marketing-email", "transactional-email",
        "forms", "marketing-events",
    ],
))

_register(OAuthProvider(
    name="salesforce",
    authorization_url="https://login.salesforce.com/services/oauth2/authorize",
    token_url="https://login.salesforce.com/services/oauth2/token",
    scopes=["api", "refresh_token"],
))

_register(OAuthProvider(
    name="pipedrive",
    authorization_url="https://oauth.pipedrive.com/oauth/authorize",
    token_url="https://oauth.pipedrive.com/oauth/token",
))

_register(OAuthProvider(
    name="copper",
    authorization_url="https://app.copper.com/oauth/authorize",
    token_url="https://app.copper.com/oauth/token",
))

# ---------------------------------------------------------------------------
# Developer Tools
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="github",
    authorization_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    scopes=["repo", "read:org", "read:user"],
))

_register(OAuthProvider(
    name="gitlab",
    authorization_url="https://gitlab.com/oauth/authorize",
    token_url="https://gitlab.com/oauth/token",
    scopes=["read_api", "read_user", "read_repository"],
))

_register(OAuthProvider(
    name="bitbucket",
    authorization_url="https://bitbucket.org/site/oauth2/authorize",
    token_url="https://bitbucket.org/site/oauth2/access_token",
))

_register(OAuthProvider(
    name="linear",
    authorization_url="https://linear.app/oauth/authorize",
    token_url="https://api.linear.app/oauth/token",
    scopes=["read"],
))

_register(OAuthProvider(
    name="sentry",
    authorization_url="https://sentry.io/oauth/authorize/",
    token_url="https://sentry.io/oauth/token/",
    scopes=["project:read", "org:read", "event:read"],
))

_register(OAuthProvider(
    name="vercel",
    authorization_url="https://vercel.com/oauth/authorize",
    token_url="https://api.vercel.com/v2/oauth/access_token",
))

_register(OAuthProvider(
    name="netlify",
    authorization_url="https://app.netlify.com/authorize",
    token_url="https://api.netlify.com/oauth/token",
))

# ---------------------------------------------------------------------------
# Communication & Support
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="slack",
    authorization_url="https://slack.com/oauth/v2/authorize",
    token_url="https://slack.com/api/oauth.v2.access",
    scopes=[
        "channels:history", "channels:read", "users:read",
        "users:read.email", "team:read",
    ],
))

_register(OAuthProvider(
    name="discord",
    authorization_url="https://discord.com/oauth2/authorize",
    token_url="https://discord.com/api/oauth2/token",
    scopes=["identify", "guilds", "guilds.members.read"],
))

_register(OAuthProvider(
    name="intercom",
    authorization_url="https://app.intercom.com/oauth",
    token_url="https://api.intercom.io/auth/eagle/token",
))

_register(OAuthProvider(
    name="front",
    authorization_url="https://app.frontapp.com/oauth/authorize",
    token_url="https://app.frontapp.com/oauth/token",
))

_register(OAuthProvider(
    name="zendesk",
    authorization_url="https://{subdomain}.zendesk.com/oauth/authorizations/new",
    token_url="https://{subdomain}.zendesk.com/oauth/tokens",
    scopes=["read", "tickets:read", "users:read"],
))

_register(OAuthProvider(
    name="helpscout",
    authorization_url="https://secure.helpscout.net/authentication/authorizeClientApplication",
    token_url="https://api.helpscout.net/v2/oauth2/token",
))

# ---------------------------------------------------------------------------
# Productivity & Project Management
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="notion",
    authorization_url="https://api.notion.com/v1/oauth/authorize",
    token_url="https://api.notion.com/v1/oauth/token",
    extra_authorize_params={"owner": "user"},
))

_register(OAuthProvider(
    name="airtable",
    authorization_url="https://airtable.com/oauth2/v1/authorize",
    token_url="https://airtable.com/oauth2/v1/token",
    scopes=["data.records:read", "schema.bases:read"],
))

_register(OAuthProvider(
    name="asana",
    authorization_url="https://app.asana.com/-/oauth_authorize",
    token_url="https://app.asana.com/-/oauth_token",
))

_register(OAuthProvider(
    name="clickup",
    authorization_url="https://app.clickup.com/api",
    token_url="https://api.clickup.com/api/v2/oauth/token",
))

_register(OAuthProvider(
    name="monday",
    authorization_url="https://auth.monday.com/oauth2/authorize",
    token_url="https://auth.monday.com/oauth2/token",
))

_register(OAuthProvider(
    name="todoist",
    authorization_url="https://todoist.com/oauth/authorize",
    token_url="https://todoist.com/oauth/access_token",
    scopes=["data:read"],
))

_register(OAuthProvider(
    name="trello",
    authorization_url="https://trello.com/1/authorize",
    token_url="https://trello.com/1/OAuthGetAccessToken",
    scopes=["read"],
))

# ---------------------------------------------------------------------------
# E-commerce
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="shopify",
    authorization_url="https://{shop}.myshopify.com/admin/oauth/authorize",
    token_url="https://{shop}.myshopify.com/admin/oauth/access_token",
    scopes=["read_products", "read_orders", "read_customers"],
))

_register(OAuthProvider(
    name="bigcommerce",
    authorization_url="https://login.bigcommerce.com/oauth2/authorize",
    token_url="https://login.bigcommerce.com/oauth2/token",
    scopes=["store_v2_products_read_only", "store_v2_orders_read_only"],
))

_register(OAuthProvider(
    name="square",
    authorization_url="https://connect.squareup.com/oauth2/authorize",
    token_url="https://connect.squareup.com/oauth2/token",
    scopes=[
        "CUSTOMERS_READ", "ORDERS_READ", "PAYMENTS_READ",
        "ITEMS_READ", "INVENTORY_READ",
    ],
))

_register(OAuthProvider(
    name="woocommerce",
    authorization_url="https://{shop}/wc-auth/v1/authorize",
    token_url="https://{shop}/wc-auth/v1/authorize",
    scopes=["read"],
))

# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="mailchimp",
    authorization_url="https://login.mailchimp.com/oauth2/authorize",
    token_url="https://login.mailchimp.com/oauth2/token",
))

_register(OAuthProvider(
    name="facebook_ads",
    authorization_url="https://www.facebook.com/v19.0/dialog/oauth",
    token_url="https://graph.facebook.com/v19.0/oauth/access_token",
    scopes=["ads_read", "ads_management", "read_insights"],
))

# ---------------------------------------------------------------------------
# Finance & Billing
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="quickbooks",
    authorization_url="https://appcenter.intuit.com/connect/oauth2",
    token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
    scopes=["com.intuit.quickbooks.accounting"],
))

_register(OAuthProvider(
    name="xero",
    authorization_url="https://login.xero.com/identity/connect/authorize",
    token_url="https://identity.xero.com/connect/token",
    scopes=["openid", "profile", "email", "accounting.transactions.read",
            "accounting.contacts.read", "accounting.settings.read"],
))

# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="gusto",
    authorization_url="https://api.gusto.com/oauth/authorize",
    token_url="https://api.gusto.com/oauth/token",
))

_register(OAuthProvider(
    name="lever",
    authorization_url="https://auth.lever.co/authorize",
    token_url="https://auth.lever.co/oauth/token",
    scopes=["offline_access", "opportunities:read:admin", "postings:read:admin"],
))

# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="figma",
    authorization_url="https://www.figma.com/oauth",
    token_url="https://api.figma.com/v1/oauth/token",
    scopes=["files:read"],
))

# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="contentful",
    authorization_url="https://be.contentful.com/oauth/authorize",
    token_url="https://be.contentful.com/oauth/token",
    scopes=["content_management_read"],
))

_register(OAuthProvider(
    name="wordpress",
    authorization_url="https://public-api.wordpress.com/oauth2/authorize",
    token_url="https://public-api.wordpress.com/oauth2/token",
))

# ---------------------------------------------------------------------------
# Google (shared OAuth, different scopes per product)
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="google_sheets",
    authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
))

_register(OAuthProvider(
    name="google_analytics",
    authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
))

_register(OAuthProvider(
    name="google_ads",
    authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/adwords"],
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
))

# ---------------------------------------------------------------------------
# Incident Management
# ---------------------------------------------------------------------------

_register(OAuthProvider(
    name="pagerduty",
    authorization_url="https://app.pagerduty.com/oauth/authorize",
    token_url="https://app.pagerduty.com/oauth/token",
    scopes=["read"],
))
