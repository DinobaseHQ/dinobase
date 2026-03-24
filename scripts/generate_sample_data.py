#!/usr/bin/env python3
"""Generate realistic sample Stripe + HubSpot data as parquet files.

Creates a shared pool of ~200 people with overlapping emails for cross-source joins.
~80% appear in both systems, ~10% only Stripe, ~10% only HubSpot.

Stripe schema matches Stripe Sigma (amounts in cents, IDs like cus_XXX).
HubSpot schema matches CRM API v3 (numeric IDs, amounts in dollars).
"""

import random
import string
import uuid
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
# Shared pool of people
# ---------------------------------------------------------------------------

NUM_PEOPLE = 200
BOTH_RATIO = 0.80  # appear in both systems
STRIPE_ONLY_RATIO = 0.10
HUBSPOT_ONLY_RATIO = 0.10

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
    ("plan_starter", "Starter", 2900, "month"),       # $29/mo
    ("plan_pro", "Pro", 9900, "month"),                # $99/mo
    ("plan_business", "Business", 29900, "month"),     # $299/mo
    ("plan_enterprise", "Enterprise", 99900, "month"), # $999/mo
    ("plan_starter_yr", "Starter Annual", 29000, "year"),   # $290/yr
    ("plan_pro_yr", "Pro Annual", 99000, "year"),           # $990/yr
]

DEAL_STAGES = [
    "appointmentscheduled",
    "qualifiedtobuy",
    "presentationscheduled",
    "decisionmakerboughtin",
    "contractsent",
    "closedwon",
    "closedlost",
]

LIFECYCLE_STAGES = ["subscriber", "lead", "marketingqualifiedlead",
                    "salesqualifiedlead", "opportunity", "customer", "evangelist"]

LEAD_STATUSES = ["new", "open", "in_progress", "open_deal", "unqualified",
                 "attempted_to_contact", "connected", "bad_timing"]


def rand_id(prefix: str, length: int = 14) -> str:
    chars = string.ascii_letters + string.digits
    return f"{prefix}_{''.join(random.choices(chars, k=length))}"


def rand_date(start_year: int = 2024, end_year: int = 2026) -> datetime:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 3, 1)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


# Generate people
people = []
for i in range(NUM_PEOPLE):
    company = random.choice(COMPANIES)
    first = fake.first_name()
    last = fake.last_name()
    domain = company[1]
    email = f"{first.lower()}.{last.lower()}@{domain}"
    created = rand_date()

    people.append({
        "first": first,
        "last": last,
        "email": email,
        "company_name": company[0],
        "company_domain": company[1],
        "company_industry": company[2],
        "company_revenue": company[3],
        "company_employees": company[4],
        "created": created,
    })

# Assign to systems
random.shuffle(people)
n_both = int(NUM_PEOPLE * BOTH_RATIO)
n_stripe_only = int(NUM_PEOPLE * STRIPE_ONLY_RATIO)

in_stripe = people[:n_both + n_stripe_only]
in_hubspot = people[:n_both] + people[n_both + n_stripe_only:]

# ---------------------------------------------------------------------------
# Stripe data
# ---------------------------------------------------------------------------

# Customers
stripe_customers = []
for p in in_stripe:
    stripe_customers.append({
        "id": rand_id("cus"),
        "email": p["email"],
        "name": f"{p['first']} {p['last']}",
        "description": f"Customer at {p['company_name']}",
        "created": int(p["created"].timestamp()),
        "currency": "usd",
        "delinquent": random.random() < 0.05,
        "livemode": True,
    })

# Subscriptions (70% of customers have one)
stripe_subscriptions = []
for cust in stripe_customers:
    if random.random() < 0.70:
        plan = random.choice(PLANS)
        created = datetime.fromtimestamp(cust["created"]) + timedelta(days=random.randint(0, 30))
        status = random.choices(
            ["active", "canceled", "past_due", "trialing"],
            weights=[0.65, 0.15, 0.10, 0.10],
        )[0]
        canceled_at = None
        if status == "canceled":
            canceled_at = int((created + timedelta(days=random.randint(30, 365))).timestamp())

        period_start = created
        if plan[3] == "month":
            period_end = created + timedelta(days=30)
        else:
            period_end = created + timedelta(days=365)

        stripe_subscriptions.append({
            "id": rand_id("sub"),
            "customer_id": cust["id"],
            "status": status,
            "plan_id": plan[0],
            "plan_amount": plan[2],
            "plan_interval": plan[3],
            "current_period_start": int(period_start.timestamp()),
            "current_period_end": int(period_end.timestamp()),
            "created": int(created.timestamp()),
            "canceled_at": canceled_at,
        })

# Charges (1-5 per customer)
stripe_charges = []
for cust in stripe_customers:
    n_charges = random.randint(1, 5)
    cust_created = datetime.fromtimestamp(cust["created"])
    for _ in range(n_charges):
        charge_date = cust_created + timedelta(days=random.randint(0, 400))
        amount = random.choice([2900, 9900, 29900, 99900, 4900, 14900, 49900])
        status = random.choices(
            ["succeeded", "failed", "pending"],
            weights=[0.90, 0.07, 0.03],
        )[0]
        stripe_charges.append({
            "id": rand_id("ch"),
            "customer_id": cust["id"],
            "amount": amount,
            "currency": "usd",
            "status": status,
            "created": int(charge_date.timestamp()),
            "payment_method_type": random.choice(["card", "card", "card", "bank_transfer", "sepa_debit"]),
            "description": random.choice([
                "Subscription payment",
                "Invoice payment",
                "One-time charge",
                None,
            ]),
        })

# Invoices (1 per subscription)
stripe_invoices = []
for sub in stripe_subscriptions:
    inv_date = datetime.fromtimestamp(sub["created"])
    status = "paid" if sub["status"] in ("active", "trialing") else random.choice(["paid", "open", "void"])
    stripe_invoices.append({
        "id": rand_id("in"),
        "customer_id": sub["customer_id"],
        "subscription_id": sub["id"],
        "amount_due": sub["plan_amount"],
        "amount_paid": sub["plan_amount"] if status == "paid" else 0,
        "status": status,
        "created": int(inv_date.timestamp()),
        "due_date": int((inv_date + timedelta(days=30)).timestamp()),
        "period_start": sub["current_period_start"],
        "period_end": sub["current_period_end"],
    })


# ---------------------------------------------------------------------------
# HubSpot data
# ---------------------------------------------------------------------------

# Companies (dedup by domain)
seen_domains = set()
hubspot_companies = []
company_id_map = {}  # domain -> id
for p in in_hubspot:
    if p["company_domain"] not in seen_domains:
        seen_domains.add(p["company_domain"])
        cid = len(hubspot_companies) + 1001
        company_id_map[p["company_domain"]] = cid
        hubspot_companies.append({
            "id": str(cid),
            "name": p["company_name"],
            "domain": p["company_domain"],
            "industry": p["company_industry"],
            "annualrevenue": float(p["company_revenue"]),
            "numberofemployees": p["company_employees"],
            "city": fake.city(),
            "state": fake.state_abbr(),
            "country": "US",
            "createdate": p["created"].isoformat(),
        })

# Contacts
hubspot_contacts = []
contact_id_counter = 5001
for p in in_hubspot:
    lifecycle = random.choice(LIFECYCLE_STAGES)
    # Customers in HubSpot if they're also in Stripe
    if p in in_stripe[:n_both]:
        lifecycle = random.choices(
            ["customer", "opportunity", "salesqualifiedlead", "evangelist"],
            weights=[0.60, 0.20, 0.15, 0.05],
        )[0]

    hs_created = p["created"] + timedelta(days=random.randint(-15, 15))
    hubspot_contacts.append({
        "id": str(contact_id_counter),
        "email": p["email"],
        "firstname": p["first"],
        "lastname": p["last"],
        "phone": fake.phone_number(),
        "company": p["company_name"],
        "company_id": str(company_id_map.get(p["company_domain"], "")),
        "lifecyclestage": lifecycle,
        "hs_lead_status": random.choice(LEAD_STATUSES),
        "createdate": hs_created.isoformat(),
        "lastmodifieddate": (hs_created + timedelta(days=random.randint(1, 200))).isoformat(),
    })
    contact_id_counter += 1

# Deals (0-2 per contact, more for customers)
hubspot_deals = []
deal_id_counter = 9001
for contact in hubspot_contacts:
    n_deals = random.choices([0, 1, 2], weights=[0.30, 0.50, 0.20])[0]
    if contact["lifecyclestage"] == "customer":
        n_deals = max(n_deals, 1)  # customers always have at least 1 deal

    for _ in range(n_deals):
        stage = random.choice(DEAL_STAGES)
        if contact["lifecyclestage"] == "customer":
            stage = random.choices(
                DEAL_STAGES,
                weights=[0.05, 0.05, 0.05, 0.05, 0.10, 0.60, 0.10],
            )[0]

        amount = round(random.choice([
            500, 1000, 2500, 5000, 10000, 15000, 25000, 50000, 75000, 100000
        ]) * random.uniform(0.8, 1.3))

        deal_created = datetime.fromisoformat(contact["createdate"]) + timedelta(days=random.randint(5, 90))
        close_date = deal_created + timedelta(days=random.randint(14, 180))

        hubspot_deals.append({
            "id": str(deal_id_counter),
            "dealname": f"{contact['company']} - {random.choice(['New Business', 'Renewal', 'Expansion', 'Upsell'])}",
            "amount": float(amount),
            "dealstage": stage,
            "pipeline": "default",
            "closedate": close_date.isoformat(),
            "createdate": deal_created.isoformat(),
            "contact_id": contact["id"],
            "company_id": contact["company_id"],
            "hubspot_owner_id": str(random.choice([101, 102, 103, 104, 105])),
        })
        deal_id_counter += 1


# ---------------------------------------------------------------------------
# Write to parquet
# ---------------------------------------------------------------------------

def write_parquet(data: list[dict], filename: str) -> None:
    if not data:
        return
    table = pa.Table.from_pylist(data)
    path = OUTPUT_DIR / filename
    pq.write_table(table, path)
    print(f"  {filename}: {len(data)} rows")


print(f"Generating sample data in {OUTPUT_DIR}/\n")

print("Stripe tables:")
write_parquet(stripe_customers, "stripe_customers.parquet")
write_parquet(stripe_subscriptions, "stripe_subscriptions.parquet")
write_parquet(stripe_charges, "stripe_charges.parquet")
write_parquet(stripe_invoices, "stripe_invoices.parquet")

print("\nHubSpot tables:")
write_parquet(hubspot_contacts, "hubspot_contacts.parquet")
write_parquet(hubspot_companies, "hubspot_companies.parquet")
write_parquet(hubspot_deals, "hubspot_deals.parquet")

# Print some stats
both_emails = set(c["email"] for c in stripe_customers) & set(c["email"] for c in hubspot_contacts)
print(f"\nCross-source stats:")
print(f"  Stripe customers:  {len(stripe_customers)}")
print(f"  HubSpot contacts:  {len(hubspot_contacts)}")
print(f"  Shared emails:     {len(both_emails)} ({len(both_emails)/len(stripe_customers)*100:.0f}% of Stripe)")
print(f"  Stripe-only:       {len(stripe_customers) - len(both_emails)}")
print(f"  HubSpot-only:      {len(hubspot_contacts) - len(both_emails)}")
print(f"\nTotal rows across all tables:")
total = (len(stripe_customers) + len(stripe_subscriptions) + len(stripe_charges) +
         len(stripe_invoices) + len(hubspot_contacts) + len(hubspot_companies) +
         len(hubspot_deals))
print(f"  {total}")
