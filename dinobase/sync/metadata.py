"""Metadata extraction from source APIs at sync time.

Each source provides field-level metadata (descriptions, types, enum values)
that we extract during sync and store as annotations in _dinobase.columns.

This replaces hardcoded annotations — metadata comes from the source of truth.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


def extract_stripe_metadata(
    api_key: str, tables: list[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract field metadata from Stripe's OpenAPI spec.

    Stripe publishes a machine-readable spec with descriptions, types, enums,
    and format hints for every field. We fetch it once and parse only the
    schemas we need.

    Returns: {table_name: {column_name: {"description": ..., "note": ...}}}
    """
    spec = _fetch_stripe_openapi_spec()
    if spec is None:
        print("  Warning: Could not fetch Stripe OpenAPI spec, skipping metadata", file=sys.stderr)
        return {}

    schemas = spec.get("components", {}).get("schemas", {})

    # Map our table names to Stripe schema names
    table_to_schema = {
        "customers": "customer",
        "subscriptions": "subscription",
        "charges": "charge",
        "invoices": "invoice",
        "products": "product",
        "prices": "price",
        "payment_intents": "payment_intent",
    }

    annotations: dict[str, dict[str, dict[str, str]]] = {}
    for table in tables:
        schema_name = table_to_schema.get(table)
        if not schema_name or schema_name not in schemas:
            continue

        schema = schemas[schema_name]
        properties = schema.get("properties", {})
        annotations[table] = {}

        for field_name, field_spec in properties.items():
            ann = _parse_openapi_field(field_spec)
            if ann:
                annotations[table][field_name] = ann

    return annotations


def extract_hubspot_metadata(
    api_key: str, tables: list[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract field metadata from HubSpot's Properties API.

    HubSpot returns live property metadata including descriptions, types,
    enum values, and custom fields — directly from the user's portal.

    Returns: {table_name: {column_name: {"description": ..., "note": ...}}}
    """
    # Map our table names to HubSpot object types
    table_to_object = {
        "contacts": "contacts",
        "companies": "companies",
        "deals": "deals",
        "tickets": "tickets",
    }

    annotations: dict[str, dict[str, dict[str, str]]] = {}
    for table in tables:
        object_type = table_to_object.get(table)
        if not object_type:
            continue

        properties = _fetch_hubspot_properties(api_key, object_type)
        if properties is None:
            continue

        annotations[table] = {}
        for prop in properties:
            ann = _parse_hubspot_property(prop)
            if ann:
                annotations[table][prop["name"]] = ann

    return annotations


def extract_postgres_metadata(
    connection_string: str, schema: str, tables: list[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract column comments and constraints from Postgres.

    Uses information_schema and pg_catalog to get column comments,
    foreign key relationships, and constraint info.

    Returns: {table_name: {column_name: {"description": ..., "note": ...}}}
    """
    try:
        import sqlalchemy
        engine = sqlalchemy.create_engine(connection_string)
    except Exception:
        return {}

    annotations: dict[str, dict[str, dict[str, str]]] = {}
    try:
        with engine.connect() as conn:
            for table in tables:
                annotations[table] = {}

                # Get column comments
                result = conn.execute(sqlalchemy.text(
                    "SELECT c.column_name, pgd.description AS comment "
                    "FROM information_schema.columns c "
                    "LEFT JOIN pg_catalog.pg_statio_all_tables st "
                    "  ON c.table_schema = st.schemaname AND c.table_name = st.relname "
                    "LEFT JOIN pg_catalog.pg_description pgd "
                    "  ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position "
                    "WHERE c.table_schema = :schema AND c.table_name = :table"
                ), {"schema": schema, "table": table})

                for row in result:
                    if row.comment:
                        annotations[table][row.column_name] = {
                            "description": row.comment
                        }

                # Get foreign key info
                result = conn.execute(sqlalchemy.text(
                    "SELECT kcu.column_name, "
                    "  ccu.table_name AS foreign_table, "
                    "  ccu.column_name AS foreign_column "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name = kcu.constraint_name "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON tc.constraint_name = ccu.constraint_name "
                    "WHERE tc.constraint_type = 'FOREIGN KEY' "
                    "  AND tc.table_schema = :schema AND tc.table_name = :table"
                ), {"schema": schema, "table": table})

                for row in result:
                    col = row.column_name
                    if col not in annotations[table]:
                        annotations[table][col] = {}
                    annotations[table][col]["note"] = (
                        f"Foreign key → {row.foreign_table}.{row.foreign_column}"
                    )
    except Exception as e:
        print(f"  Warning: Could not extract Postgres metadata: {e}", file=sys.stderr)

    return annotations


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_stripe_spec_cache: dict | None = None


def _fetch_stripe_openapi_spec() -> dict | None:
    """Fetch and cache Stripe's OpenAPI spec.

    Tries to fetch the full spec from GitHub. Falls back to a bundled
    mini-spec (sample_data/stripe_openapi_mini.json) if the network is
    unavailable.
    """
    global _stripe_spec_cache
    if _stripe_spec_cache is not None:
        return _stripe_spec_cache

    url = "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json"
    try:
        print("  Fetching Stripe OpenAPI spec for metadata...", file=sys.stderr)
        import ssl
        ctx = ssl.create_default_context()
        req = Request(url, headers={"User-Agent": "dinobase/0.1"})
        try:
            with urlopen(req, timeout=30, context=ctx) as resp:
                _stripe_spec_cache = json.loads(resp.read())
                return _stripe_spec_cache
        except (URLError, OSError):
            # Retry without SSL verification as fallback
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urlopen(req, timeout=30, context=ctx) as resp:
                _stripe_spec_cache = json.loads(resp.read())
                return _stripe_spec_cache
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(f"  Warning: Failed to fetch Stripe spec: {e}", file=sys.stderr)
        # Fall back to bundled mini-spec
        return _load_bundled_stripe_spec()


def _load_bundled_stripe_spec() -> dict | None:
    """Load the bundled mini Stripe OpenAPI spec."""
    bundled_paths = [
        Path(__file__).parent.parent.parent.parent / "sample_data" / "stripe_openapi_mini.json",
        Path.home() / ".dinobase" / "stripe_openapi_mini.json",
    ]
    for path in bundled_paths:
        if path.exists():
            try:
                with open(path) as f:
                    spec = json.load(f)
                    print(f"  Using bundled Stripe spec from {path}", file=sys.stderr)
                    return spec
            except (json.JSONDecodeError, OSError):
                continue
    print("  Warning: No Stripe metadata available (no network, no bundled spec)", file=sys.stderr)
    return None


def _parse_openapi_field(field_spec: dict) -> dict[str, str] | None:
    """Parse an OpenAPI field spec into a {description, note} annotation."""
    # Handle $ref and anyOf by extracting the description at this level
    description = field_spec.get("description", "")
    if not description:
        return None

    # Clean up markdown links: [text](url) -> text
    import re
    description = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', description)
    # Truncate very long descriptions
    if len(description) > 300:
        description = description[:297] + "..."

    ann: dict[str, str] = {"description": description}

    # Build note from type info
    notes = []
    fmt = field_spec.get("format")
    if fmt == "unix-time":
        notes.append("Unix timestamp (seconds since epoch). Use to_timestamp() to convert.")

    enum_values = field_spec.get("enum")
    if enum_values and len(enum_values) <= 15:
        notes.append(f"Values: {', '.join(str(v) for v in enum_values)}")

    if field_spec.get("nullable"):
        notes.append("Can be null")

    if notes:
        ann["note"] = " ".join(notes)

    return ann


def _fetch_hubspot_properties(api_key: str, object_type: str) -> list[dict] | None:
    """Fetch properties for a HubSpot object type."""
    url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"
    try:
        req = Request(url, headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "dinobase/0.1",
        })
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("results", [])
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(f"  Warning: Failed to fetch HubSpot {object_type} properties: {e}", file=sys.stderr)
        return None


def _parse_hubspot_property(prop: dict) -> dict[str, str] | None:
    """Parse a HubSpot property into a {description, note} annotation."""
    label = prop.get("label", "")
    description = prop.get("description", "")
    prop_type = prop.get("type", "")

    # Use label as description if description is empty
    desc = description if description else label
    if not desc:
        return None

    ann: dict[str, str] = {"description": desc}

    # Build note from type/options info
    notes = []

    options = prop.get("options", [])
    visible_options = [o for o in options if not o.get("hidden", False)]
    if visible_options and len(visible_options) <= 15:
        values = [f"{o['value']} ({o['label']})" if o.get("label") != o.get("value") else o["value"]
                  for o in visible_options]
        notes.append(f"Values: {', '.join(values)}")

    if prop_type == "datetime":
        notes.append("ISO 8601 timestamp")
    elif prop_type == "date":
        notes.append("Date (YYYY-MM-DD)")
    elif prop_type == "number":
        notes.append("Numeric")

    if prop.get("calculated"):
        formula = prop.get("calculationFormula", "")
        if formula:
            notes.append(f"Calculated: {formula[:100]}")
        else:
            notes.append("Calculated by HubSpot")

    if not prop.get("hubspotDefined", True):
        notes.append("Custom property")

    if notes:
        ann["note"] = " | ".join(notes)

    return ann
