#!/usr/bin/env python3
"""Generate realistic sample data for 5 benchmark verticals as parquet files.

Verticals:
  1. RevOps     — HubSpot CRM + Stripe billing
  2. E-commerce — Shopify + Stripe payments
  3. Knowledge  — Notion + GitHub + Slack
  4. DevOps     — GitHub PRs + PagerDuty + Datadog
  5. Support    — Zendesk + Stripe + product analytics

Each vertical has cross-source join keys (email or username) with ~80% overlap.
All monetary amounts in Stripe are in cents; other sources use dollars.
"""

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

OUTPUT_DIR = Path(__file__).parent.parent / "sample_data"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_id(prefix: str, length: int = 14) -> str:
    chars = string.ascii_letters + string.digits
    return f"{prefix}_{''.join(random.choices(chars, k=length))}"


def rand_date(start_year: int = 2024, end_year: int = 2026) -> datetime:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 3, 1)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def write_parquet(data: list[dict], filename: str) -> None:
    if not data:
        return
    table = pa.Table.from_pylist(data)
    path = OUTPUT_DIR / filename
    pq.write_table(table, path)
    print(f"  {filename}: {len(data)} rows")


# ---------------------------------------------------------------------------
# Shared pools
# ---------------------------------------------------------------------------

COMPANIES = [
    ("Acme Corp", "acme.com", "Technology", 5_000_000, 45),
    ("Globex Industries", "globex.io", "Manufacturing", 12_000_000, 120),
    ("Initech", "initech.com", "Technology", 3_500_000, 30),
    ("Umbrella Corp", "umbrella.co", "Healthcare", 25_000_000, 250),
    ("Stark Industries", "starkindustries.com", "Technology", 50_000_000, 500),
    ("Wayne Enterprises", "wayne-ent.com", "Finance", 40_000_000, 400),
    ("Hooli", "hooli.com", "Technology", 8_000_000, 80),
    ("Pied Piper", "piedpiper.com", "Technology", 2_000_000, 20),
    ("Dunder Mifflin", "dundermifflin.com", "Retail", 1_500_000, 25),
    ("Sterling Cooper", "sterlingcooper.com", "Marketing", 6_000_000, 55),
    ("Wonka Industries", "wonka.co", "Food & Beverage", 15_000_000, 150),
    ("Cyberdyne Systems", "cyberdyne.io", "Technology", 30_000_000, 300),
    ("Massive Dynamic", "massivedynamic.com", "Technology", 20_000_000, 200),
    ("Soylent Corp", "soylent.co", "Food & Beverage", 7_000_000, 70),
    ("Tyrell Corp", "tyrell.com", "Technology", 35_000_000, 350),
    ("LexCorp", "lexcorp.com", "Finance", 45_000_000, 450),
    ("Oscorp", "oscorp.io", "Healthcare", 18_000_000, 180),
    ("Weyland-Yutani", "weyland.co", "Manufacturing", 60_000_000, 600),
    ("Aperture Science", "aperture.io", "Technology", 10_000_000, 100),
    ("Black Mesa", "blackmesa.com", "Technology", 9_000_000, 90),
]

PLANS = [
    ("plan_starter", "Starter", 2900, "month"),
    ("plan_pro", "Pro", 9900, "month"),
    ("plan_business", "Business", 29900, "month"),
    ("plan_enterprise", "Enterprise", 99900, "month"),
    ("plan_starter_yr", "Starter Annual", 29000, "year"),
    ("plan_pro_yr", "Pro Annual", 99000, "year"),
]

DEAL_STAGES = [
    "appointmentscheduled", "qualifiedtobuy", "presentationscheduled",
    "decisionmakerboughtin", "contractsent", "closedwon", "closedlost",
]

LIFECYCLE_STAGES = [
    "subscriber", "lead", "marketingqualifiedlead",
    "salesqualifiedlead", "opportunity", "customer", "evangelist",
]

LEAD_STATUSES = [
    "new", "open", "in_progress", "open_deal", "unqualified",
    "attempted_to_contact", "connected", "bad_timing",
]


def make_people(n: int = 200) -> list[dict]:
    """Generate a shared pool of people with company assignments."""
    people = []
    for _ in range(n):
        company = random.choice(COMPANIES)
        first = fake.first_name()
        last = fake.last_name()
        email = f"{first.lower()}.{last.lower()}@{company[1]}"
        username = f"{first.lower()}{last.lower()}{random.randint(1, 99)}"
        people.append({
            "first": first, "last": last, "email": email, "username": username,
            "company_name": company[0], "company_domain": company[1],
            "company_industry": company[2], "company_revenue": company[3],
            "company_employees": company[4], "created": rand_date(),
        })
    return people


def split_sources(people, both=0.80, a_only=0.10):
    """Split people into two overlapping groups for cross-source simulation."""
    random.shuffle(people)
    n_both = int(len(people) * both)
    n_a_only = int(len(people) * a_only)
    source_a = people[:n_both + n_a_only]
    source_b = people[:n_both] + people[n_both + n_a_only:]
    return source_a, source_b


# =========================================================================
# VERTICAL 1: RevOps (HubSpot + Stripe)
# =========================================================================

def generate_revops():
    print("\n=== VERTICAL 1: RevOps ===")
    people = make_people(200)
    in_stripe, in_hubspot = split_sources(people)
    n_both = int(200 * 0.80)

    # --- Stripe ---
    stripe_customers = []
    for p in in_stripe:
        stripe_customers.append({
            "id": rand_id("cus"), "email": p["email"],
            "name": f"{p['first']} {p['last']}",
            "description": f"Customer at {p['company_name']}",
            "created": int(p["created"].timestamp()),
            "currency": "usd", "delinquent": random.random() < 0.05,
            "livemode": True,
        })

    stripe_subscriptions = []
    for cust in stripe_customers:
        if random.random() < 0.70:
            plan = random.choice(PLANS)
            created = datetime.fromtimestamp(cust["created"]) + timedelta(days=random.randint(0, 30))
            status = random.choices(["active", "canceled", "past_due", "trialing"], weights=[0.65, 0.15, 0.10, 0.10])[0]
            canceled_at = int((created + timedelta(days=random.randint(30, 365))).timestamp()) if status == "canceled" else None
            period_end = created + timedelta(days=30 if plan[3] == "month" else 365)
            stripe_subscriptions.append({
                "id": rand_id("sub"), "customer_id": cust["id"], "status": status,
                "plan_id": plan[0], "plan_amount": plan[2], "plan_interval": plan[3],
                "current_period_start": int(created.timestamp()),
                "current_period_end": int(period_end.timestamp()),
                "created": int(created.timestamp()), "canceled_at": canceled_at,
            })

    stripe_charges = []
    for cust in stripe_customers:
        for _ in range(random.randint(1, 5)):
            charge_date = datetime.fromtimestamp(cust["created"]) + timedelta(days=random.randint(0, 400))
            stripe_charges.append({
                "id": rand_id("ch"), "customer_id": cust["id"],
                "amount": random.choice([2900, 9900, 29900, 99900, 4900, 14900, 49900]),
                "currency": "usd",
                "status": random.choices(["succeeded", "failed", "pending"], weights=[0.90, 0.07, 0.03])[0],
                "created": int(charge_date.timestamp()),
                "payment_method_type": random.choice(["card", "card", "card", "bank_transfer", "sepa_debit"]),
                "description": random.choice(["Subscription payment", "Invoice payment", "One-time charge", None]),
            })

    stripe_invoices = []
    for sub in stripe_subscriptions:
        inv_date = datetime.fromtimestamp(sub["created"])
        status = "paid" if sub["status"] in ("active", "trialing") else random.choice(["paid", "open", "void"])
        stripe_invoices.append({
            "id": rand_id("in"), "customer_id": sub["customer_id"],
            "subscription_id": sub["id"], "amount_due": sub["plan_amount"],
            "amount_paid": sub["plan_amount"] if status == "paid" else 0,
            "status": status, "created": int(inv_date.timestamp()),
            "due_date": int((inv_date + timedelta(days=30)).timestamp()),
            "period_start": sub["current_period_start"],
            "period_end": sub["current_period_end"],
        })

    # --- HubSpot ---
    seen_domains = set()
    hubspot_companies = []
    company_id_map = {}
    for p in in_hubspot:
        if p["company_domain"] not in seen_domains:
            seen_domains.add(p["company_domain"])
            cid = len(hubspot_companies) + 1001
            company_id_map[p["company_domain"]] = cid
            hubspot_companies.append({
                "id": str(cid), "name": p["company_name"], "domain": p["company_domain"],
                "industry": p["company_industry"], "annualrevenue": float(p["company_revenue"]),
                "numberofemployees": p["company_employees"], "city": fake.city(),
                "state": fake.state_abbr(), "country": "US", "createdate": p["created"].isoformat(),
            })

    hubspot_contacts = []
    cid = 5001
    for p in in_hubspot:
        lifecycle = random.choice(LIFECYCLE_STAGES)
        if p in in_stripe[:n_both]:
            lifecycle = random.choices(["customer", "opportunity", "salesqualifiedlead", "evangelist"], weights=[0.60, 0.20, 0.15, 0.05])[0]
        hubspot_contacts.append({
            "id": str(cid), "email": p["email"], "firstname": p["first"], "lastname": p["last"],
            "phone": fake.phone_number(), "company": p["company_name"],
            "company_id": str(company_id_map.get(p["company_domain"], "")),
            "lifecyclestage": lifecycle, "hs_lead_status": random.choice(LEAD_STATUSES),
            "createdate": (p["created"] + timedelta(days=random.randint(-15, 15))).isoformat(),
            "lastmodifieddate": (p["created"] + timedelta(days=random.randint(1, 200))).isoformat(),
        })
        cid += 1

    hubspot_deals = []
    did = 9001
    for contact in hubspot_contacts:
        n_deals = random.choices([0, 1, 2], weights=[0.30, 0.50, 0.20])[0]
        if contact["lifecyclestage"] == "customer":
            n_deals = max(n_deals, 1)
        for _ in range(n_deals):
            stage = random.choice(DEAL_STAGES)
            if contact["lifecyclestage"] == "customer":
                stage = random.choices(DEAL_STAGES, weights=[0.05, 0.05, 0.05, 0.05, 0.10, 0.60, 0.10])[0]
            amount = round(random.choice([500, 1000, 2500, 5000, 10000, 15000, 25000, 50000, 75000, 100000]) * random.uniform(0.8, 1.3))
            deal_created = datetime.fromisoformat(contact["createdate"]) + timedelta(days=random.randint(5, 90))
            hubspot_deals.append({
                "id": str(did), "dealname": f"{contact['company']} - {random.choice(['New Business', 'Renewal', 'Expansion', 'Upsell'])}",
                "amount": float(amount), "dealstage": stage, "pipeline": "default",
                "closedate": (deal_created + timedelta(days=random.randint(14, 180))).isoformat(),
                "createdate": deal_created.isoformat(), "contact_id": contact["id"],
                "company_id": contact["company_id"],
                "hubspot_owner_id": str(random.choice([101, 102, 103, 104, 105])),
            })
            did += 1

    print("Stripe tables:")
    write_parquet(stripe_customers, "stripe_customers.parquet")
    write_parquet(stripe_subscriptions, "stripe_subscriptions.parquet")
    write_parquet(stripe_charges, "stripe_charges.parquet")
    write_parquet(stripe_invoices, "stripe_invoices.parquet")
    print("HubSpot tables:")
    write_parquet(hubspot_contacts, "hubspot_contacts.parquet")
    write_parquet(hubspot_companies, "hubspot_companies.parquet")
    write_parquet(hubspot_deals, "hubspot_deals.parquet")

    both_emails = set(c["email"] for c in stripe_customers) & set(c["email"] for c in hubspot_contacts)
    print(f"  Cross-source overlap: {len(both_emails)} shared emails ({len(both_emails)/len(stripe_customers)*100:.0f}%)")


# =========================================================================
# VERTICAL 2: E-commerce (Shopify + Stripe)
# =========================================================================

PRODUCT_TYPES = ["T-Shirt", "Hoodie", "Mug", "Sticker Pack", "Poster", "Hat", "Tote Bag", "Phone Case", "Notebook", "Water Bottle"]
VENDORS = ["Acme Merch", "PrintCo", "GearUp", "SwagHouse", "BrandLab"]

def generate_ecommerce():
    print("\n=== VERTICAL 2: E-commerce ===")
    people = make_people(180)
    in_shopify, in_stripe = split_sources(people, both=0.85, a_only=0.08)

    # --- Shopify products ---
    products = []
    for i in range(50):
        base_price = random.choice([9.99, 14.99, 19.99, 24.99, 29.99, 34.99, 49.99, 79.99, 99.99])
        products.append({
            "id": f"prod_{i+1:04d}", "title": f"{random.choice(['Classic', 'Premium', 'Limited', 'Custom', 'Vintage'])} {random.choice(PRODUCT_TYPES)}",
            "vendor": random.choice(VENDORS), "product_type": random.choice(PRODUCT_TYPES),
            "status": random.choices(["active", "draft", "archived"], weights=[0.80, 0.10, 0.10])[0],
            "price": base_price, "inventory_quantity": random.randint(0, 500),
            "created_at": rand_date().isoformat(),
        })

    # --- Shopify customers ---
    shopify_customers = []
    for p in in_shopify:
        orders_count = random.choices([0, 1, 2, 3, 5, 8], weights=[0.15, 0.30, 0.25, 0.15, 0.10, 0.05])[0]
        shopify_customers.append({
            "id": f"cust_{rand_id('', 8)}", "email": p["email"],
            "first_name": p["first"], "last_name": p["last"],
            "orders_count": orders_count,
            "total_spent": round(orders_count * random.uniform(15, 120), 2),
            "created_at": p["created"].isoformat(),
            "tags": random.choice(["vip", "wholesale", "retail", "new", ""]),
        })

    # --- Shopify orders ---
    orders = []
    for cust in shopify_customers:
        for i in range(cust["orders_count"]):
            product = random.choice(products)
            qty = random.randint(1, 4)
            total = round(product["price"] * qty, 2)
            order_date = datetime.fromisoformat(cust["created_at"]) + timedelta(days=random.randint(1, 300))
            financial = random.choices(["paid", "refunded", "pending", "partially_refunded"], weights=[0.82, 0.08, 0.05, 0.05])[0]
            fulfillment = random.choices(["fulfilled", "unfulfilled", "partial"], weights=[0.75, 0.15, 0.10])[0]
            orders.append({
                "id": f"order_{rand_id('', 8)}", "order_number": 1000 + len(orders),
                "email": cust["email"], "total_price": total, "subtotal_price": round(total * 0.9, 2),
                "financial_status": financial, "fulfillment_status": fulfillment,
                "created_at": order_date.isoformat(), "product_id": product["id"],
                "line_items_count": qty,
            })

    # --- Stripe (payments) ---
    stripe_ecom_customers = []
    for p in in_stripe:
        stripe_ecom_customers.append({
            "id": rand_id("cus"), "email": p["email"],
            "name": f"{p['first']} {p['last']}",
            "created": int(p["created"].timestamp()),
        })

    cust_by_email = {c["email"]: c["id"] for c in stripe_ecom_customers}
    stripe_ecom_charges = []
    for order in orders:
        if order["email"] in cust_by_email and order["financial_status"] in ("paid", "partially_refunded"):
            stripe_ecom_charges.append({
                "id": rand_id("ch"), "customer_id": cust_by_email[order["email"]],
                "amount": int(order["total_price"] * 100),  # dollars to cents!
                "currency": "usd",
                "status": "succeeded" if order["financial_status"] == "paid" else "refunded",
                "created": int(datetime.fromisoformat(order["created_at"]).timestamp()),
            })

    print("Shopify tables:")
    write_parquet(products, "shopify_products.parquet")
    write_parquet(shopify_customers, "shopify_customers.parquet")
    write_parquet(orders, "shopify_orders.parquet")
    print("Stripe (ecom) tables:")
    write_parquet(stripe_ecom_customers, "stripe_ecom_customers.parquet")
    write_parquet(stripe_ecom_charges, "stripe_ecom_charges.parquet")
    overlap = set(c["email"] for c in shopify_customers) & set(c["email"] for c in stripe_ecom_customers)
    print(f"  Cross-source overlap: {len(overlap)} shared emails")


# =========================================================================
# VERTICAL 3: Knowledge Base (Notion + GitHub + Slack)
# =========================================================================

LANGUAGES = ["Python", "TypeScript", "Go", "Rust", "Java", "Ruby", "C++"]
ISSUE_LABELS = ["bug", "feature", "enhancement", "documentation", "good first issue", "priority:high", "priority:low"]
SLACK_TOPICS = ["engineering", "product", "design", "support", "random", "announcements", "incidents", "standups"]

def generate_knowledge():
    print("\n=== VERTICAL 3: Knowledge Base ===")
    # Use usernames as cross-source key
    usernames = [f"{fake.first_name().lower()}{fake.last_name().lower()}{random.randint(1,99)}" for _ in range(60)]

    repo_names = [
        "api-gateway", "web-frontend", "mobile-app", "data-pipeline", "auth-service",
        "billing-engine", "notification-service", "search-indexer", "admin-dashboard", "cli-tool",
        "sdk-python", "sdk-node", "infrastructure", "docs", "design-system",
        "ml-models", "monitoring", "load-balancer", "cache-layer", "event-bus",
        "user-service", "analytics-engine", "payment-processor", "email-service", "file-storage",
        "test-framework", "ci-pipeline", "feature-flags", "rate-limiter", "queue-worker",
    ]

    # --- Notion ---
    databases = []
    for i, name in enumerate(["Engineering Wiki", "Product Specs", "Design System", "Onboarding", "Architecture Decisions",
                               "API Docs", "Runbooks", "Sprint Planning", "Retrospectives", "Team Directory",
                               "Vendor Evaluations", "Security Policies", "Compliance", "Release Notes", "FAQ"]):
        databases.append({
            "id": f"db_{i+1:03d}", "title": name,
            "description": f"Collection of {name.lower()} documents",
            "created_time": rand_date(2024, 2025).isoformat(),
        })

    pages = []
    for i in range(200):
        db = random.choice(databases)
        author = random.choice(usernames[:45])  # 45 of 60 users write docs
        created = rand_date()
        pages.append({
            "id": f"page_{i+1:04d}", "title": fake.sentence(nb_words=random.randint(3, 8)).rstrip("."),
            "parent_id": db["id"], "created_by": author,
            "created_time": created.isoformat(),
            "last_edited_time": (created + timedelta(days=random.randint(0, 90))).isoformat(),
            "status": random.choices(["published", "draft", "archived"], weights=[0.70, 0.20, 0.10])[0],
            "word_count": random.randint(50, 5000),
        })

    # --- GitHub ---
    repos = []
    for i, name in enumerate(repo_names):
        repos.append({
            "id": f"repo_{i+1:03d}", "name": name, "full_name": f"acme/{name}",
            "private": random.random() < 0.3,
            "language": random.choice(LANGUAGES),
            "stargazers_count": random.randint(0, 500),
            "open_issues_count": random.randint(0, 50),  # NOTE: this is a stale field, may not match actual count
            "created_at": rand_date(2023, 2025).isoformat(),
            "pushed_at": rand_date(2025, 2026).isoformat(),
        })

    issues = []
    for i in range(300):
        repo = random.choice(repos)
        author = random.choice(usernames[:50])
        created = rand_date()
        state = random.choices(["open", "closed"], weights=[0.35, 0.65])[0]
        issues.append({
            "id": f"issue_{i+1:04d}", "repo_id": repo["id"],
            "title": fake.sentence(nb_words=random.randint(4, 10)).rstrip("."),
            "state": state, "author": author,
            "labels": ",".join(random.sample(ISSUE_LABELS, k=random.randint(0, 3))),
            "created_at": created.isoformat(),
            "closed_at": (created + timedelta(days=random.randint(1, 60))).isoformat() if state == "closed" else None,
            "comments_count": random.randint(0, 25),
        })

    # --- Slack ---
    channels = []
    for i in range(40):
        topic = random.choice(SLACK_TOPICS)
        channels.append({
            "id": f"ch_{i+1:03d}",
            "name": f"{topic}-{random.choice(['general', 'team', 'alerts', 'discussion', fake.word()])}",
            "topic": topic, "num_members": random.randint(3, 80),
            "created": int(rand_date(2023, 2025).timestamp()),
            "is_archived": random.random() < 0.15,
        })

    messages = []
    for i in range(800):
        ch = random.choice(channels)
        user = random.choice(usernames)
        ts = rand_date()
        is_thread = random.random() < 0.30
        messages.append({
            "id": f"msg_{i+1:05d}", "channel_id": ch["id"], "user": user,
            "text_length": random.randint(5, 2000),
            "ts": ts.isoformat(),
            "thread_ts": (ts - timedelta(hours=random.randint(1, 48))).isoformat() if is_thread else None,
            "reactions_count": random.choices([0, 0, 0, 1, 2, 3, 5, 10], weights=[0.50, 0.15, 0.10, 0.08, 0.07, 0.05, 0.03, 0.02])[0],
        })

    print("Notion tables:")
    write_parquet(databases, "notion_databases.parquet")
    write_parquet(pages, "notion_pages.parquet")
    print("GitHub tables:")
    write_parquet(repos, "github_repos.parquet")
    write_parquet(issues, "github_issues.parquet")
    print("Slack tables:")
    write_parquet(channels, "slack_channels.parquet")
    write_parquet(messages, "slack_messages.parquet")
    overlap = set(p["created_by"] for p in pages) & set(i["author"] for i in issues)
    print(f"  Cross-source overlap: {len(overlap)} shared usernames (Notion<>GitHub)")


# =========================================================================
# VERTICAL 4: DevOps (GitHub PRs + PagerDuty + Datadog)
# =========================================================================

SERVICE_NAMES = [
    "api-gateway", "auth-service", "billing-engine", "web-frontend", "data-pipeline",
    "notification-service", "search-indexer", "payment-processor", "user-service",
    "analytics-engine", "cache-layer", "event-bus", "queue-worker", "file-storage",
    "email-service", "rate-limiter", "load-balancer", "monitoring-agent", "ci-runner", "dns-resolver",
]

def generate_devops():
    print("\n=== VERTICAL 4: DevOps ===")
    usernames = [f"{fake.first_name().lower()}{random.randint(1,99)}" for _ in range(40)]

    repo_names = SERVICE_NAMES[:15]

    # --- GitHub PRs ---
    pull_requests = []
    for i in range(250):
        repo = random.choice(repo_names)
        author = random.choice(usernames)
        created = rand_date()
        state = random.choices(["open", "closed", "merged"], weights=[0.15, 0.10, 0.75])[0]
        merged_at = (created + timedelta(hours=random.randint(1, 72))).isoformat() if state == "merged" else None
        pull_requests.append({
            "id": f"pr_{i+1:04d}", "repo_id": repo,
            "title": fake.sentence(nb_words=random.randint(4, 8)).rstrip("."),
            "state": state, "author": author,
            "created_at": created.isoformat(), "merged_at": merged_at,
            "additions": random.randint(1, 2000), "deletions": random.randint(0, 500),
            "review_comments": random.randint(0, 15),
            "head_branch": random.choice(["feature/", "fix/", "chore/", "refactor/"]) + fake.word(),
        })

    # --- GitHub Deployments ---
    deployments = []
    for i in range(150):
        repo = random.choice(repo_names)
        created = rand_date()
        deployments.append({
            "id": f"deploy_{i+1:04d}", "repo_id": repo,
            "environment": random.choices(["production", "staging"], weights=[0.6, 0.4])[0],
            "status": random.choices(["success", "failure", "pending"], weights=[0.80, 0.15, 0.05])[0],
            "created_at": created.isoformat(),
            "sha": "".join(random.choices("0123456789abcdef", k=7)),
        })

    # --- PagerDuty ---
    pd_services = []
    for i, name in enumerate(SERVICE_NAMES):
        pd_services.append({
            "id": f"svc_{i+1:03d}", "name": name,
            "description": f"Monitoring for {name.replace('-', ' ')}",
            "status": random.choices(["active", "maintenance", "disabled"], weights=[0.85, 0.10, 0.05])[0],
            "team_id": f"team_{random.randint(1, 5):02d}",
        })

    incidents = []
    for i in range(100):
        svc = random.choice(pd_services)
        created = rand_date()
        status = random.choices(["triggered", "acknowledged", "resolved"], weights=[0.10, 0.15, 0.75])[0]
        resolved_at = (created + timedelta(minutes=random.randint(5, 1440))).isoformat() if status == "resolved" else None
        incidents.append({
            "id": f"inc_{i+1:04d}", "service_id": svc["id"],
            "title": f"{random.choice(['High latency', 'Error rate spike', 'CPU usage', 'Memory leak', 'Connection timeout', 'Disk full', '5xx errors'])} on {svc['name']}",
            "status": status, "urgency": random.choices(["high", "low"], weights=[0.40, 0.60])[0],
            "created_at": created.isoformat(), "resolved_at": resolved_at,
            "escalation_count": random.choices([0, 1, 2, 3], weights=[0.50, 0.30, 0.15, 0.05])[0],
        })

    # --- Datadog ---
    monitors = []
    for i in range(50):
        svc = random.choice(pd_services)
        monitors.append({
            "id": f"mon_{i+1:03d}",
            "name": f"{random.choice(['Latency', 'Error Rate', 'CPU', 'Memory', 'Request Count'])} - {svc['name']}",
            "type": random.choice(["metric", "log", "apm", "synthetics"]),
            "status": random.choices(["OK", "Alert", "Warn", "No Data"], weights=[0.60, 0.15, 0.15, 0.10])[0],
            "service_tag": svc["name"],
            "last_triggered": rand_date().isoformat() if random.random() < 0.4 else None,
        })

    print("GitHub tables:")
    write_parquet(pull_requests, "github_pull_requests.parquet")
    write_parquet(deployments, "github_deployments.parquet")
    print("PagerDuty tables:")
    write_parquet(pd_services, "pagerduty_services.parquet")
    write_parquet(incidents, "pagerduty_incidents.parquet")
    print("Datadog tables:")
    write_parquet(monitors, "datadog_monitors.parquet")
    # Cross-source: service names link PagerDuty services, Datadog monitors, and GitHub repos
    pd_svc_names = set(s["name"] for s in pd_services)
    dd_svc_names = set(m["service_tag"] for m in monitors)
    gh_repos = set(pr["repo_id"] for pr in pull_requests)
    print(f"  Cross-source overlap: {len(pd_svc_names & dd_svc_names)} services (PD<>DD), {len(pd_svc_names & gh_repos)} repos (PD<>GH)")


# =========================================================================
# VERTICAL 5: Customer Support (Zendesk + Stripe + Analytics)
# =========================================================================

TICKET_SUBJECTS = [
    "Can't log in to my account", "Billing issue - double charged", "Feature request: export to CSV",
    "App crashes on startup", "How do I upgrade my plan?", "Data not syncing", "Slow performance",
    "Password reset not working", "Invoice missing", "API rate limit too low",
    "Integration with Slack broken", "Mobile app not loading", "Wrong amount on invoice",
    "Can't add team members", "Dashboard showing wrong data", "Webhook not firing",
    "SSO configuration help", "Data export taking too long", "Account locked out",
    "Cancellation request", "Refund request", "Bug: duplicate notifications",
]

EVENT_NAMES = ["page_view", "feature_used", "error", "login", "signup", "upgrade", "downgrade", "api_call"]

def generate_support():
    print("\n=== VERTICAL 5: Customer Support ===")
    people = make_people(220)
    in_zendesk, in_stripe = split_sources(people, both=0.75, a_only=0.12)

    # --- Zendesk ---
    agents = []
    for i in range(25):
        agents.append({
            "id": f"agent_{i+1:03d}", "name": fake.name(),
            "email": fake.email(), "role": random.choices(["agent", "admin", "lead"], weights=[0.70, 0.15, 0.15])[0],
            "group_name": random.choice(["Tier 1", "Tier 2", "Billing", "Technical", "Enterprise"]),
        })

    tickets = []
    for i in range(400):
        requester = random.choice(in_zendesk)
        agent = random.choice(agents)
        created = rand_date()
        status = random.choices(["new", "open", "pending", "solved", "closed"], weights=[0.05, 0.15, 0.10, 0.40, 0.30])[0]
        solved_at = (created + timedelta(hours=random.randint(1, 168))).isoformat() if status in ("solved", "closed") else None
        sat = random.choices(["good", "bad", "offered", "unoffered"], weights=[0.45, 0.10, 0.20, 0.25])[0]
        if status in ("new", "open", "pending"):
            sat = "unoffered"
        tickets.append({
            "id": f"ticket_{i+1:05d}", "subject": random.choice(TICKET_SUBJECTS),
            "status": status,
            "priority": random.choices(["low", "normal", "high", "urgent"], weights=[0.15, 0.45, 0.25, 0.15])[0],
            "requester_email": requester["email"], "assignee_id": agent["id"],
            "created_at": created.isoformat(), "solved_at": solved_at,
            "satisfaction_rating": sat,
            "tags": ",".join(random.sample(["billing", "bug", "feature_request", "account", "integration", "performance"], k=random.randint(0, 2))),
        })

    # --- Analytics events ---
    events = []
    for i in range(1000):
        user = random.choice(people)
        events.append({
            "id": f"evt_{i+1:05d}", "user_email": user["email"],
            "event_name": random.choices(EVENT_NAMES, weights=[0.35, 0.25, 0.08, 0.15, 0.03, 0.02, 0.02, 0.10])[0],
            "timestamp": rand_date().isoformat(),
        })

    # --- Stripe (support context) ---
    support_plans = ["free", "starter", "pro", "business", "enterprise"]
    plan_prices = {"free": 0, "starter": 2900, "pro": 9900, "business": 29900, "enterprise": 99900}

    stripe_support_customers = []
    for p in in_stripe:
        plan = random.choices(support_plans, weights=[0.10, 0.25, 0.30, 0.20, 0.15])[0]
        stripe_support_customers.append({
            "id": rand_id("cus"), "email": p["email"],
            "name": f"{p['first']} {p['last']}",
            "plan": plan, "mrr_cents": plan_prices[plan],
            "created": int(p["created"].timestamp()),
        })

    stripe_support_subs = []
    for cust in stripe_support_customers:
        if cust["mrr_cents"] > 0:
            stripe_support_subs.append({
                "id": rand_id("sub"), "customer_id": cust["id"],
                "status": random.choices(["active", "canceled", "past_due", "trialing"], weights=[0.70, 0.12, 0.08, 0.10])[0],
                "plan_amount": cust["mrr_cents"],
                "plan_interval": "month",
                "created": cust["created"],
            })

    print("Zendesk tables:")
    write_parquet(agents, "zendesk_agents.parquet")
    write_parquet(tickets, "zendesk_tickets.parquet")
    print("Analytics tables:")
    write_parquet(events, "analytics_events.parquet")
    print("Stripe (support) tables:")
    write_parquet(stripe_support_customers, "stripe_support_customers.parquet")
    write_parquet(stripe_support_subs, "stripe_support_subscriptions.parquet")
    overlap = set(t["requester_email"] for t in tickets) & set(c["email"] for c in stripe_support_customers)
    print(f"  Cross-source overlap: {len(overlap)} shared emails (Zendesk<>Stripe)")


# =========================================================================
# Main
# =========================================================================

if __name__ == "__main__":
    print(f"Generating sample data in {OUTPUT_DIR}/")

    generate_revops()
    generate_ecommerce()
    generate_knowledge()
    generate_devops()
    generate_support()

    # Summary
    parquet_files = list(OUTPUT_DIR.glob("*.parquet"))
    total_rows = 0
    print(f"\n{'='*50}")
    print(f"SUMMARY: {len(parquet_files)} parquet files generated")
    for f in sorted(parquet_files):
        import pyarrow.parquet as pq2
        t = pq2.read_table(f)
        total_rows += len(t)
    print(f"Total rows across all tables: {total_rows}")
