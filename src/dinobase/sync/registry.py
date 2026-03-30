"""Source registry — maps source names to dlt verified sources and REST API configs.

Adding a new source = adding an entry to SOURCES. No Python connector code needed.
dlt handles auth, pagination, rate limiting, incremental loading.

Three types of sources:
1. dlt verified sources (import_path = "sources.X.Y") — battle-tested, community maintained
2. dlt built-in sources (import_path = "dlt.sources.X.Y") — sql_database, filesystem
3. REST API configs (import_path = "dlt.sources.rest_api.rest_api_source") — any REST API via config
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CredentialParam:
    """Describes a credential parameter for a source."""
    name: str                      # param name in the dlt source function
    cli_flag: str                  # e.g. "--api-key"
    env_var: str | None = None     # e.g. "HUBSPOT_API_KEY"
    prompt: str | None = None      # interactive prompt text
    secret: bool = True            # hide input when prompting


@dataclass
class SourceEntry:
    """Registry entry for a dlt source."""
    name: str                      # dinobase source name (e.g., "hubspot")
    import_path: str               # e.g., "sources.hubspot.hubspot"
    credentials: list[CredentialParam]
    pip_extra: str | None = None   # extra pip package needed
    description: str = ""
    extra_params: dict[str, Any] = field(default_factory=dict)
    metadata_openapi_url: str | None = None
    rest_api_config: dict[str, Any] | None = None  # for rest_api_source based connectors
    graphql_config: dict[str, Any] | None = None   # for graphql_source based connectors
    supports_oauth: bool = False   # whether this source can be connected via OAuth
    live_fetch_config: dict[str, Any] | None = None  # API config for single-record live fetch
    credential_help: str | None = None  # where to find credentials (for agents)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON output (used by `dinobase sources --available`)."""
        return {
            "name": self.name,
            "description": self.description,
            "supports_oauth": self.supports_oauth,
            "credential_help": self.credential_help,
            "credentials": [
                {
                    "name": p.name,
                    "cli_flag": p.cli_flag,
                    "env_var": p.env_var,
                    "prompt": p.prompt,
                    "secret": p.secret,
                }
                for p in self.credentials
            ],
            "pip_extra": self.pip_extra,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SOURCES: dict[str, SourceEntry] = {}


def _register(entry: SourceEntry) -> None:
    SOURCES[entry.name] = entry


def _register_rest_api(
    name: str,
    description: str,
    base_url: str,
    auth_type: str,
    auth_field: str,
    resources: list[dict],
    cli_flag: str = "--api-key",
    env_var: str | None = None,
    prompt: str | None = None,
    paginator: dict | None = None,
    pip_extra: str | None = None,
    data_selector: str | None = None,
    extra_credentials: list[CredentialParam] | None = None,
) -> None:
    """Register a source backed by dlt's rest_api_source."""
    creds = [
        CredentialParam(auth_field, cli_flag, env_var, prompt or f"{name} API key")
    ]
    if extra_credentials:
        creds.extend(extra_credentials)

    config: dict[str, Any] = {
        "client": {
            "base_url": base_url,
        },
        "resources": resources,
    }

    if paginator:
        config["client"]["paginator"] = paginator

    resource_defaults: dict[str, Any] = {"primary_key": "id", "write_disposition": "merge"}
    if data_selector:
        resource_defaults["endpoint"] = {"data_selector": data_selector}
    config["resource_defaults"] = resource_defaults

    _register(SourceEntry(
        name=name,
        import_path="dlt.sources.rest_api.rest_api_source",
        description=description,
        credentials=creds,
        pip_extra=pip_extra,
        rest_api_config=config,
    ))


def _load_yaml_api_configs(apis_dir: Path | None = None) -> None:
    """Load REST API and GraphQL source configs from YAML files in the configs/ directory."""
    if apis_dir is None:
        apis_dir = Path(__file__).parent / "sources" / "configs"
    if not apis_dir.is_dir():
        return

    for yaml_path in sorted(apis_dir.glob("*.yaml")):
        try:
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)

            if cfg.get("type") == "graphql":
                _load_yaml_graphql(cfg)
            else:
                _load_yaml_rest_api(cfg)
        except Exception:
            pass  # skip broken configs silently


def _build_credentials(cfg: dict[str, Any]) -> list[CredentialParam]:
    """Build credential list from a YAML config.

    Supports two formats:
    - New: top-level `credentials` list with name/flag/env/prompt/secret
    - Legacy: top-level `auth` dict with field/cli_flag/env_var + `extra_credentials`
    """
    # New format: credentials list
    if "credentials" in cfg:
        creds = []
        for c in cfg["credentials"]:
            creds.append(CredentialParam(
                name=c["name"],
                cli_flag=c.get("flag", f"--{c['name'].replace('_', '-')}"),
                env_var=c.get("env"),
                prompt=c.get("prompt"),
                secret=c.get("secret", True),
            ))
        return creds

    # Legacy format: auth dict
    auth = cfg["auth"]
    creds = [
        CredentialParam(
            name=auth["field"],
            cli_flag=auth.get("cli_flag", "--api-key"),
            env_var=auth.get("env_var"),
            prompt=auth.get("prompt", f"{cfg['name']} API key"),
            secret=auth.get("secret", True),
        )
    ]
    for extra in cfg.get("extra_credentials", []):
        creds.append(CredentialParam(
            name=extra["name"],
            cli_flag=extra["cli_flag"],
            env_var=extra.get("env_var"),
            prompt=extra.get("prompt"),
            secret=extra.get("secret", True),
        ))
    return creds


def _load_yaml_rest_api(cfg: dict[str, Any]) -> None:
    """Register a REST API source from a parsed YAML config.

    Supports two formats:
    - New: client.auth, client.paginator, credentials list
    - Legacy: top-level auth/paginator, auth dict with field/cli_flag
    """
    creds = _build_credentials(cfg)
    client = cfg.get("client", {})

    client_cfg: dict[str, Any] = {
        "base_url": client.get("base_url", ""),
    }
    if not client_cfg["base_url"]:
        raise ValueError(f"No base_url for {cfg.get('name', 'unknown')}")

    # Auth: prefer client.auth, fall back to building from top-level auth
    if "auth" in client:
        client_cfg["auth"] = client["auth"]

    # Headers
    if "headers" in client:
        client_cfg["headers"] = client["headers"]

    # Paginator: prefer client.paginator, fall back to top-level
    if "paginator" in client:
        client_cfg["paginator"] = client["paginator"]
    elif "paginator" in cfg:
        client_cfg["paginator"] = cfg["paginator"]

    resource_defaults: dict[str, Any] = cfg.get("resource_defaults", {
        "primary_key": "id",
        "write_disposition": "merge",
    })

    rest_api_config: dict[str, Any] = {
        "client": client_cfg,
        "resource_defaults": resource_defaults,
        "resources": cfg["resources"],
    }

    _register(SourceEntry(
        name=cfg["name"],
        import_path="dlt.sources.rest_api.rest_api_source",
        description=cfg.get("description", ""),
        credentials=creds,
        pip_extra=cfg.get("pip_extra"),
        rest_api_config=rest_api_config,
        supports_oauth=cfg.get("oauth", False),
        credential_help=cfg.get("credential_help"),
    ))


def _load_yaml_graphql(cfg: dict[str, Any]) -> None:
    """Register a GraphQL source from a parsed YAML config."""
    creds = _build_credentials(cfg)

    graphql_config: dict[str, Any] = {
        "endpoint": cfg["endpoint"],
        "resources": cfg["resources"],
    }
    if "auth_prefix" in cfg:
        graphql_config["auth_prefix"] = cfg["auth_prefix"]

    _register(SourceEntry(
        name=cfg["name"],
        import_path="dinobase.sync.sources.graphql.graphql_source",
        description=cfg.get("description", ""),
        credentials=creds,
        pip_extra=cfg.get("pip_extra"),
        graphql_config=graphql_config,
        supports_oauth=cfg.get("oauth", False),
        credential_help=cfg.get("credential_help"),
    ))


# Load YAML-based REST API configs
_load_yaml_api_configs()


# ===================================================================
# dlt VERIFIED SOURCES (battle-tested, community maintained)
# ===================================================================

# --- CRM & Sales ---

_register(SourceEntry(
    name="hubspot",
    import_path="sources.hubspot.hubspot",
    description="HubSpot CRM (contacts, companies, deals, tickets)",
    credentials=[
        CredentialParam("api_key", "--api-key", "HUBSPOT_API_KEY", "HubSpot private app token"),
    ],
    supports_oauth=True,
    credential_help="HubSpot > Settings > Integrations > Private Apps > create app > copy token",
    live_fetch_config={
        "client": {
            "base_url": "https://api.hubapi.com",
            "auth": {"type": "bearer", "token": "{api_key}"},
        },
        "resources": [
            {"name": "contacts", "endpoint": {"path": "crm/v3/objects/contacts"}},
            {"name": "companies", "endpoint": {"path": "crm/v3/objects/companies"}},
            {"name": "deals", "endpoint": {"path": "crm/v3/objects/deals"}},
            {"name": "tickets", "endpoint": {"path": "crm/v3/objects/tickets"}},
            {"name": "products", "endpoint": {"path": "crm/v3/objects/products"}},
            {"name": "quotes", "endpoint": {"path": "crm/v3/objects/quotes"}},
            {"name": "owners", "endpoint": {"path": "crm/v3/owners"}},
        ],
    },
))

_register(SourceEntry(
    name="pipedrive",
    import_path="sources.pipedrive.pipedrive_source",
    description="Pipedrive CRM (deals, persons, organizations, activities)",
    credentials=[
        CredentialParam("pipedrive_api_key", "--api-key", "PIPEDRIVE_API_KEY", "Pipedrive API key"),
    ],
    supports_oauth=True,
))

_register(SourceEntry(
    name="salesforce",
    import_path="sources.salesforce.salesforce_source",
    description="Salesforce CRM",
    pip_extra="simple_salesforce",
    credentials=[
        CredentialParam("username", "--username", "SALESFORCE_USERNAME", "Salesforce username", secret=False),
        CredentialParam("password", "--password", "SALESFORCE_PASSWORD", "Salesforce password"),
        CredentialParam("security_token", "--security-token", "SALESFORCE_SECURITY_TOKEN", "Salesforce security token"),
    ],
    supports_oauth=True,
))

# --- Payments & Billing ---

_register(SourceEntry(
    name="stripe",
    import_path="sources.stripe_analytics.stripe_source",
    description="Stripe payments (customers, subscriptions, charges, invoices)",
    credentials=[
        CredentialParam("stripe_secret_key", "--api-key", "STRIPE_SECRET_KEY", "Stripe secret key"),
    ],
    credential_help="Stripe Dashboard > Developers > API keys (use the Secret key, starts with sk_)",
    metadata_openapi_url="https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
    live_fetch_config={
        "client": {
            "base_url": "https://api.stripe.com/v1",
            "auth": {"type": "bearer", "token": "{stripe_secret_key}"},
        },
        "resources": [
            {"name": "customers", "endpoint": {"path": "customers"}},
            {"name": "customer", "endpoint": {"path": "customers"}},
            {"name": "subscriptions", "endpoint": {"path": "subscriptions"}},
            {"name": "subscription", "endpoint": {"path": "subscriptions"}},
            {"name": "charges", "endpoint": {"path": "charges"}},
            {"name": "charge", "endpoint": {"path": "charges"}},
            {"name": "invoices", "endpoint": {"path": "invoices"}},
            {"name": "invoice", "endpoint": {"path": "invoices"}},
            {"name": "products", "endpoint": {"path": "products"}},
            {"name": "product", "endpoint": {"path": "products"}},
            {"name": "prices", "endpoint": {"path": "prices"}},
            {"name": "price", "endpoint": {"path": "prices"}},
            {"name": "payment_intents", "endpoint": {"path": "payment_intents"}},
            {"name": "payment_intent", "endpoint": {"path": "payment_intents"}},
            {"name": "events", "endpoint": {"path": "events"}},
            {"name": "event", "endpoint": {"path": "events"}},
        ],
    },
))

# --- Developer Tools ---

_register(SourceEntry(
    name="github",
    import_path="sources.github.github_reactions",
    description="GitHub (repos, issues, PRs, reactions, stargazers)",
    credentials=[
        CredentialParam("access_token", "--token", "GITHUB_TOKEN", "GitHub personal access token"),
    ],
    supports_oauth=True,
    credential_help="GitHub > Settings > Developer settings > Personal access tokens > Generate",
    live_fetch_config={
        "client": {
            "base_url": "https://api.github.com",
            "auth": {"type": "bearer", "token": "{access_token}"},
        },
        "resources": [
            {"name": "issues", "endpoint": {"path": "repos/{owner}/{repo}/issues"}},
            {"name": "pull_requests", "endpoint": {"path": "repos/{owner}/{repo}/pulls"}},
            {"name": "stargazers", "endpoint": {"path": "repos/{owner}/{repo}/stargazers"}},
        ],
    },
))

_register(SourceEntry(
    name="jira",
    import_path="sources.jira.jira",
    description="Jira (issues, projects, users)",
    credentials=[
        CredentialParam("subdomain", "--subdomain", "JIRA_SUBDOMAIN", "Jira subdomain", secret=False),
        CredentialParam("email", "--email", "JIRA_EMAIL", "Jira account email", secret=False),
        CredentialParam("api_token", "--api-token", "JIRA_API_TOKEN", "Jira API token"),
    ],
    credential_help="Atlassian account > Security > API tokens > Create API token",
    live_fetch_config={
        "client": {
            "base_url": "https://{subdomain}.atlassian.net/rest/api/3",
            "auth": {"type": "http_basic", "username": "{email}", "password": "{api_token}"},
        },
        "resources": [
            {"name": "issues", "endpoint": {"path": "issue"}},
            {"name": "projects", "endpoint": {"path": "project"}},
            {"name": "users", "endpoint": {"path": "user"}},
        ],
    },
))

# --- Communication ---

_register(SourceEntry(
    name="slack",
    import_path="sources.slack.slack_source",
    description="Slack (channels, messages, users)",
    credentials=[
        CredentialParam("access_token", "--token", "SLACK_TOKEN", "Slack bot token"),
    ],
    supports_oauth=True,
    credential_help="Slack API > Your Apps > OAuth & Permissions > Bot User OAuth Token",
))

_register(SourceEntry(
    name="zendesk",
    import_path="sources.zendesk.zendesk_support",
    description="Zendesk Support (tickets, users, organizations)",
    credentials=[
        CredentialParam("credentials", "--token", "ZENDESK_TOKEN", "Zendesk API token"),
    ],
    supports_oauth=True,
))

# --- E-commerce ---

_register(SourceEntry(
    name="shopify",
    import_path="sources.shopify_dlt.shopify_source",
    description="Shopify (orders, products, customers)",
    credentials=[
        CredentialParam("private_app_password", "--api-key", "SHOPIFY_API_KEY", "Shopify private app password"),
        CredentialParam("shop_url", "--shop-url", "SHOPIFY_SHOP_URL", "Shopify shop URL", secret=False),
    ],
    supports_oauth=True,
    credential_help="Shopify Admin > Settings > Apps > Develop apps > Create an app > API credentials",
))

# --- Productivity ---

_register(SourceEntry(
    name="notion",
    import_path="sources.notion.notion_databases",
    description="Notion databases",
    credentials=[
        CredentialParam("api_key", "--api-key", "NOTION_API_KEY", "Notion integration token"),
    ],
    supports_oauth=True,
    credential_help="Notion > Settings > Connections > Develop or manage integrations > Create > copy token",
    live_fetch_config={
        "client": {
            "base_url": "https://api.notion.com/v1",
            "auth": {"type": "bearer", "token": "{api_key}"},
            "headers": {"Notion-Version": "2022-06-28"},
        },
        "resources": [
            {"name": "pages", "endpoint": {"path": "pages"}},
            {"name": "databases", "endpoint": {"path": "databases"}},
            {"name": "users", "endpoint": {"path": "users"}},
            {"name": "blocks", "endpoint": {"path": "blocks"}},
        ],
    },
))

_register(SourceEntry(
    name="airtable",
    import_path="sources.airtable.airtable_source",
    description="Airtable bases and tables",
    pip_extra="pyairtable",
    credentials=[
        CredentialParam("access_token", "--token", "AIRTABLE_TOKEN", "Airtable personal access token"),
    ],
    supports_oauth=True,
))

_register(SourceEntry(
    name="google_sheets",
    import_path="sources.google_sheets.google_spreadsheet",
    description="Google Sheets",
    pip_extra="google-api-python-client",
    credentials=[
        CredentialParam("credentials", "--credentials-file", "GOOGLE_APPLICATION_CREDENTIALS", "Path to service account JSON", secret=False),
    ],
    supports_oauth=True,
))

# --- Marketing ---

_register(SourceEntry(
    name="facebook_ads",
    import_path="sources.facebook_ads.facebook_ads_source",
    description="Facebook/Meta Ads (campaigns, ad sets, ads, insights)",
    pip_extra="facebook_business",
    credentials=[
        CredentialParam("access_token", "--token", "FACEBOOK_ACCESS_TOKEN", "Facebook access token"),
        CredentialParam("account_id", "--account-id", "FACEBOOK_ACCOUNT_ID", "Ad account ID", secret=False),
    ],
    supports_oauth=True,
))

_register(SourceEntry(
    name="google_analytics",
    import_path="sources.google_analytics.google_analytics",
    description="Google Analytics 4",
    pip_extra="google-analytics-data",
    credentials=[
        CredentialParam("property_id", "--property-id", "GA_PROPERTY_ID", "GA4 property ID", secret=False),
        CredentialParam("credentials", "--credentials-file", "GOOGLE_APPLICATION_CREDENTIALS", "Service account JSON", secret=False),
    ],
    supports_oauth=True,
))

_register(SourceEntry(
    name="google_ads",
    import_path="sources.google_ads.google_ads",
    description="Google Ads (campaigns, ad groups, ads, keywords)",
    pip_extra="google-ads",
    credentials=[
        CredentialParam("credentials", "--credentials-file", "GOOGLE_APPLICATION_CREDENTIALS", "Service account JSON", secret=False),
    ],
    supports_oauth=True,
))

# --- Support ---

_register(SourceEntry(
    name="freshdesk",
    import_path="sources.freshdesk.freshdesk_source",
    description="Freshdesk (tickets, contacts, companies)",
    credentials=[
        CredentialParam("api_secret_key", "--api-key", "FRESHDESK_API_KEY", "Freshdesk API key"),
        CredentialParam("domain", "--domain", "FRESHDESK_DOMAIN", "Freshdesk domain", secret=False),
    ],
    live_fetch_config={
        "client": {
            "base_url": "https://{domain}.freshdesk.com/api/v2",
            "auth": {"type": "http_basic", "username": "{api_secret_key}", "password": "X"},
        },
        "resources": [
            {"name": "tickets", "endpoint": {"path": "tickets"}},
            {"name": "contacts", "endpoint": {"path": "contacts"}},
            {"name": "companies", "endpoint": {"path": "companies"}},
            {"name": "agents", "endpoint": {"path": "agents"}},
        ],
    },
))

# --- Data ---

_register(SourceEntry(
    name="mongodb",
    import_path="sources.mongodb.mongodb",
    description="MongoDB collections",
    pip_extra="pymongo",
    credentials=[
        CredentialParam("connection_url", "--connection-string", "MONGODB_URL", "MongoDB connection URL"),
    ],
))

_register(SourceEntry(
    name="kafka",
    import_path="sources.kafka.kafka_consumer",
    description="Apache Kafka topics",
    pip_extra="confluent_kafka",
    credentials=[
        CredentialParam("bootstrap_servers", "--servers", "KAFKA_BOOTSTRAP_SERVERS", "Kafka bootstrap servers", secret=False),
    ],
))

_register(SourceEntry(
    name="kinesis",
    import_path="sources.kinesis.kinesis_stream",
    description="Amazon Kinesis streams",
    credentials=[
        CredentialParam("stream_name", "--stream", "KINESIS_STREAM_NAME", "Kinesis stream name", secret=False),
        CredentialParam("aws_access_key_id", "--access-key", "AWS_ACCESS_KEY_ID", "AWS access key ID"),
        CredentialParam("aws_secret_access_key", "--secret-key", "AWS_SECRET_ACCESS_KEY", "AWS secret access key"),
    ],
))

# --- HR ---

_register(SourceEntry(
    name="personio",
    import_path="sources.personio.personio_source",
    description="Personio HR (employees, absences, attendances)",
    credentials=[
        CredentialParam("client_id", "--client-id", "PERSONIO_CLIENT_ID", "Personio client ID", secret=False),
        CredentialParam("client_secret", "--client-secret", "PERSONIO_CLIENT_SECRET", "Personio client secret"),
    ],
))

_register(SourceEntry(
    name="workable",
    import_path="sources.workable.workable_source",
    description="Workable recruiting (jobs, candidates, activities)",
    credentials=[
        CredentialParam("access_token", "--token", "WORKABLE_TOKEN", "Workable access token"),
        CredentialParam("subdomain", "--subdomain", "WORKABLE_SUBDOMAIN", "Workable subdomain", secret=False),
    ],
))

# --- Project Management ---

_register(SourceEntry(
    name="asana",
    import_path="sources.asana_dlt.asana_source",
    description="Asana (workspaces, projects, tasks)",
    pip_extra="asana",
    credentials=[
        CredentialParam("access_token", "--token", "ASANA_TOKEN", "Asana personal access token"),
    ],
    supports_oauth=True,
))

# --- Content ---

_register(SourceEntry(
    name="strapi",
    import_path="sources.strapi.strapi_source",
    description="Strapi CMS",
    credentials=[
        CredentialParam("api_secret_key", "--api-key", "STRAPI_API_KEY", "Strapi API key"),
        CredentialParam("domain", "--domain", "STRAPI_DOMAIN", "Strapi domain", secret=False),
    ],
))

# --- Video ---

_register(SourceEntry(
    name="mux",
    import_path="sources.mux.assets_resource",
    description="Mux video (assets, views)",
    credentials=[
        CredentialParam("mux_api_access_token", "--access-token", "MUX_ACCESS_TOKEN", "Mux access token"),
        CredentialParam("mux_api_secret_key", "--secret-key", "MUX_SECRET_KEY", "Mux secret key"),
    ],
))

# --- Analytics ---

_register(SourceEntry(
    name="matomo",
    import_path="sources.matomo.matomo_visits",
    description="Matomo web analytics (visits, reports)",
    credentials=[
        CredentialParam("api_token", "--token", "MATOMO_TOKEN", "Matomo API token"),
        CredentialParam("url", "--url", "MATOMO_URL", "Matomo instance URL", secret=False),
    ],
))

_register(SourceEntry(
    name="bing_webmaster",
    import_path="sources.bing_webmaster.page_stats",
    description="Bing Webmaster Tools (page stats, query stats)",
    credentials=[
        CredentialParam("api_key", "--api-key", "BING_WEBMASTER_API_KEY", "Bing Webmaster API key"),
    ],
))


# ===================================================================
# DATABASES (built-in dlt sql_database — any SQLAlchemy-compatible DB)
# ===================================================================

_db_credential = CredentialParam(
    "credentials", "--connection-string", "DATABASE_URL", "Connection string"
)

for _name, _desc, _pip, _help in [
    ("postgres",    "PostgreSQL database",             None,                     "postgresql://user:password@host:5432/dbname"),
    ("mysql",       "MySQL database",                  None,                     "mysql+pymysql://user:password@host:3306/dbname"),
    ("mariadb",     "MariaDB (MySQL-compatible)",      None,                     "mysql+pymysql://user:password@host:3306/dbname"),
    ("mssql",       "Microsoft SQL Server",            "pyodbc",                 "mssql+pyodbc://user:password@host:1433/dbname?driver=ODBC+Driver+17+for+SQL+Server"),
    ("oracle",      "Oracle Database",                 "oracledb",               "oracle+oracledb://user:password@host:1521/dbname"),
    ("sqlite",      "SQLite database",                 None,                     "/path/to/database.db"),
    ("snowflake",   "Snowflake data warehouse",        "snowflake-sqlalchemy",   "snowflake://user:password@account/database/schema?warehouse=WAREHOUSE"),
    ("bigquery",    "Google BigQuery",                 "sqlalchemy-bigquery",    "bigquery://project/dataset"),
    ("redshift",    "Amazon Redshift",                 "sqlalchemy-redshift",    "postgresql://user:password@cluster.region.redshift.amazonaws.com:5439/dbname"),
    ("clickhouse",  "ClickHouse",                      "clickhouse-sqlalchemy",  "clickhouse://user:password@host:8123/dbname — port 8123 is HTTP (default). Port 9000 is the native TCP port; use clickhouse+native://host:9000/dbname for that."),
    ("cockroachdb", "CockroachDB (Postgres-compatible)", None,                   "cockroachdb://user:password@host:26257/dbname"),
    ("databricks",  "Databricks SQL warehouse",        "databricks-sql-connector", "databricks+connector://token:ACCESS_TOKEN@HOST/PATH?http_path=/sql/1.0/warehouses/ID"),
    ("trino",       "Trino (distributed SQL)",         "trino",                  "trino://user@host:8080/catalog/schema"),
    ("presto",      "PrestoDB",                        "pyhive",                 "presto://user@host:8080/catalog/schema"),
    ("duckdb_source", "DuckDB database file",          None,                     "/path/to/database.duckdb"),
]:
    _register(SourceEntry(
        name=_name,
        import_path="dlt.sources.sql_database.sql_database",
        description=_desc,
        pip_extra=_pip,
        credential_help=_help,
        credentials=[_db_credential] if _name != "sqlite" else [
            CredentialParam("credentials", "--path", None, "Path to SQLite file", secret=False),
        ],
    ))


# ===================================================================
# CLOUD STORAGE / FILESYSTEMS (built-in dlt filesystem source)
# ===================================================================

_register(SourceEntry(
    name="s3",
    import_path="dlt.sources.filesystem.filesystem",
    description="Amazon S3 bucket (sync files incrementally)",
    credentials=[
        CredentialParam("bucket_url", "--bucket-url", "S3_BUCKET_URL", "S3 URL (s3://bucket/prefix/)", secret=False),
        CredentialParam("aws_access_key_id", "--access-key", "AWS_ACCESS_KEY_ID", "AWS access key ID"),
        CredentialParam("aws_secret_access_key", "--secret-key", "AWS_SECRET_ACCESS_KEY", "AWS secret key"),
    ],
))

_register(SourceEntry(
    name="gcs",
    import_path="dlt.sources.filesystem.filesystem",
    description="Google Cloud Storage bucket (sync files incrementally)",
    credentials=[
        CredentialParam("bucket_url", "--bucket-url", "GCS_BUCKET_URL", "GCS URL (gs://bucket/prefix/)", secret=False),
        CredentialParam("credentials", "--credentials-file", "GOOGLE_APPLICATION_CREDENTIALS", "Service account JSON", secret=False),
    ],
))

_register(SourceEntry(
    name="azure",
    import_path="dlt.sources.filesystem.filesystem",
    description="Azure Blob Storage (sync files incrementally)",
    credentials=[
        CredentialParam("bucket_url", "--container-url", "AZURE_STORAGE_URL", "Azure URL (az://container/)", secret=False),
        CredentialParam("azure_storage_account_name", "--account-name", "AZURE_STORAGE_ACCOUNT_NAME", "Account name", secret=False),
        CredentialParam("azure_storage_account_key", "--account-key", "AZURE_STORAGE_ACCOUNT_KEY", "Account key"),
    ],
))

_register(SourceEntry(
    name="sftp",
    import_path="dlt.sources.filesystem.filesystem",
    description="SFTP server (sync files incrementally)",
    credentials=[
        CredentialParam("bucket_url", "--url", "SFTP_URL", "SFTP URL (sftp://host/path/)", secret=False),
        CredentialParam("sftp_username", "--username", "SFTP_USERNAME", "SFTP username", secret=False),
        CredentialParam("sftp_password", "--password", "SFTP_PASSWORD", "SFTP password"),
    ],
))


# ===================================================================
# REST API SOURCES — loaded from YAML configs in sources/configs/
# ===================================================================
# All REST API sources are now defined in YAML files under
# src/dinobase/sync/sources/configs/*.yaml and loaded by _load_yaml_api_configs().
# See CONNECTOR_SPEC skill (.claude/skills/build-connector/) for how to add more.

# --- Incident Management ---


# ===================================================================
# Lookup functions
# ===================================================================

def get_source_entry(name: str) -> SourceEntry | None:
    return SOURCES.get(name)


def list_available_sources() -> list[str]:
    return sorted(SOURCES.keys())
