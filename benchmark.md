You need benchmarks that are reproducible, demonstrably fair, and measure things developers actually care about. Here's what I'd build.

### The benchmark suite: 5 tests, 1 dataset

**Use one realistic dataset across all tests.** Synthetic but representative: a fictional SaaS company with data in Hubspot (CRM), Stripe (payments), and a product analytics source (events). Publish the dataset so anyone can reproduce.

---

### Benchmark 1: Time to first correct answer

**What it measures:** Developer experience. How long from "I have API credentials" to "an agent correctly answers a business question."

**Setup:**
- Provide Hubspot + Stripe sandbox credentials (or mock API servers)
- The question: "What's my total pipeline value by deal stage this month?"
- Clock starts when developer begins setup
- Clock stops when agent returns the correct answer

**Compare:**
| Solution | Steps required |
|---|---|
| DIY (DuckDB + dlt + MCP) | Install dlt, write sync script, configure DuckDB, write MCP server, register in Claude/Cursor, test |
| MotherDuck MCP | Set up MotherDuck account, install dlt separately, write sync script, load data, configure MCP, register, test |
| Airbyte Agent Engine | Install Airbyte connector, configure credentials, register MCP, test |
| This database | `muxed connect hubspot --credentials .env`, agent queries immediately |

**What "winning" looks like:** 10x time gap (e.g., 5 minutes vs 1 hour). If the gap is 2x, it's not compelling enough.

**How to run:** Screen-record yourself doing all four. Publish unedited. The video IS the marketing.

---

### Benchmark 2: Query accuracy (the core benchmark)

**What it measures:** Does the agent get the right answer? This is where semantics and provenance prove their value.

**Setup:**
- 30 questions across 3 difficulty tiers
- Ground truth answers pre-computed from the dataset
- Run each question 5 times per solution (LLMs are non-deterministic) and report accuracy

**Tier 1 — Single source, simple (10 questions):**
```
"How many open deals do we have?"
"What's our total revenue this month?"
"List the top 5 customers by deal value"
```
Every solution should get these right. This is the baseline.

**Tier 2 — Single source, requires understanding semantics (10 questions):**
```
"What's our MRR?" (requires knowing the formula, not just a column)
"How many deals are at risk?" (requires knowing what 'at risk' means in this pipeline)
"What's our win rate this quarter?" (requires knowing closed_won / (closed_won + closed_lost))
"Show me churned customers" (requires knowing status=2 means churned)
```
This is where semantic definitions matter. Without them, agents guess or hallucinate.

**Tier 3 — Cross-source, requires joining + semantics (10 questions):**
```
"Which customers from our highest-value deals have overdue invoices?"
"What's the revenue from deals that closed in the last 30 days?" (CRM close date + Stripe payment)
"Which sales rep's deals have the highest actual payment rate?"
"Show me customers where product usage dropped >50% but they have an active subscription"
```
This is where cross-source joins + entity resolution + semantics all matter.

**Compare:**

| Solution | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Raw DuckDB (no semantics) | ~90% | ~40% | ~20% |
| MotherDuck MCP | ~90% | ~40% | N/A (no connectors) |
| Airbyte (per-tool) | ~85% | ~50% | ~10% (no joins) |
| This DB (auto-gen semantics) | ~95% | ~70% | ~60% |
| This DB (refined semantics) | ~95% | ~85% | ~75% |

**What "winning" looks like:** Tier 1 is table stakes. The gap should appear in Tier 2 (semantics) and be dramatic in Tier 3 (cross-source). If there's no meaningful accuracy gap, the product doesn't work.

**How to publish:** Open-source the question set, the ground truth, the evaluation script, and all raw results. Let people run it themselves.

---

### Benchmark 3: Token cost per correct answer

**What it measures:** How much does it cost to get a right answer? Not just tokens per query, but tokens per *correct* query — because wrong answers that require retries are wasted tokens.

**Setup:**
- Use the same 30 questions from Benchmark 2
- Measure total tokens (input + output) per question, including retries
- Calculate: tokens per correct answer = total tokens / correct answers

**Why "per correct answer" matters:**
- Raw DuckDB might use fewer tokens per query, but if the agent fails 60% of Tier 2 questions, those are wasted tokens + human intervention time
- The DB with semantics might use slightly more tokens per query (metadata in responses) but get the answer right first time

**Compare:**

| Solution | Avg tokens/query | Accuracy | Effective cost (tokens/correct answer) |
|---|---|---|---|
| Raw DuckDB | 3,000 | 50% | 6,000 |
| This DB (with semantics + provenance) | 3,800 | 85% | 4,470 |

**What "winning" looks like:** Lower effective cost despite higher per-query tokens. The semantics pay for themselves through fewer retries and higher accuracy.

---

### Benchmark 4: Stale data detection

**What it measures:** Does the agent know when it shouldn't trust the data?

**Setup:**
- Sync data, then deliberately make one source 24 hours stale
- Ask time-sensitive questions that depend on the stale source:
  ```
  "How many deals closed today?"  (stale CRM data)
  "What's our revenue so far this week?" (stale payment data)
  ```

**Compare agent responses:**

| Solution | Response to "deals closed today?" with 24h stale CRM |
|---|---|
| Raw DuckDB | Returns yesterday's data as if it's today's. No warning. |
| MotherDuck | Same — no freshness awareness |
| Airbyte | Returns live API data (but can't join) |
| This DB | Returns data + caveat: "Warning: CRM data is 24h stale. This result may not include deals closed in the last 24 hours." |

**What "winning" looks like:** The other solutions silently return wrong answers. This DB tells the agent (and therefore the user) that the data might be unreliable. The agent can then decide to caveat its response or request a fresh sync.

**This is the most emotionally compelling benchmark.** "Your current setup gives you confidently wrong answers. Ours tells you when it's uncertain." That's a story people remember.

---

### Benchmark 5: Write-back safety (Stage 2 preview)

**What it measures:** When an agent takes action, does it understand the consequences?

**Setup:**
- Agent is asked: "Close deal #4521 as won"
- Compare what happens:

| Solution | Behavior |
|---|---|
| Raw DuckDB | `UPDATE deals SET stage = 'closed_won' WHERE id = 4521` — local DB updated, Hubspot unchanged. Data now diverged. |
| MotherDuck | Same |
| Airbyte | Can't write (read-only) |
| This DB | Shows preview: "This will update Hubspot deal #4521 to Closed Won, triggering the 'Won Deal' workflow. Confirm?" |

**This benchmark is a demo, not a measurement.** You can't quantify it, but you can show it side-by-side and the difference is obvious.

---

### Implementation plan

**Week 1: Build the dataset + question set**
- Create synthetic Hubspot + Stripe + product analytics data (or use sandbox APIs)
- Write 30 questions with ground truth answers
- Publish dataset and questions as an open-source repo

**Week 2: Run benchmarks against existing solutions**
- Set up DIY (DuckDB + dlt + MCP), MotherDuck, Airbyte
- Run all 30 questions 5x each, record tokens and accuracy
- This gives you the baseline to beat BEFORE building your product

**Week 3: Build minimal product + run against it**
- Implement: connectors + auto-generated semantics + provenance in responses
- Run the same 30 questions
- Measure the gap

**Week 4: Publish**
- Blog post: "We benchmarked 4 ways to connect agents to data. Here's what we found."
- Open-source the benchmark suite
- Screen recordings of Benchmark 1 (time to first query)
- Link to the product repo

### What the benchmark repo looks like

```
agent-data-benchmark/
├── dataset/
│   ├── hubspot_deals.parquet
│   ├── hubspot_contacts.parquet
│   ├── stripe_subscriptions.parquet
│   ├── stripe_invoices.parquet
│   └── product_events.parquet
├── questions/
│   ├── tier1_simple.json
│   ├── tier2_semantic.json
│   └── tier3_cross_source.json
├── ground_truth/
│   └── answers.json
├── eval/
│   ├── run_benchmark.py
│   ├── score_results.py
│   └── token_counter.py
├── solutions/
│   ├── raw_duckdb/
│   ├── motherduck/
│   ├── airbyte/
│   └── muxed/
├── results/
│   └── (raw outputs from each run)
└── README.md
```

### The one benchmark that matters most

If you only have time for one: **Benchmark 2, Tier 2 questions.** These are the questions where semantic awareness makes or breaks accuracy. If your auto-generated semantics don't measurably improve accuracy on questions like "What's our MRR?" and "Show me churned customers," the core thesis is wrong and you should find out now, not after building the full product.