# ShippyPro prospecting and campaign audit

This public repository contains code, schema and configuration examples. Prospect datasets, contact details, provider receipts, SQLite databases and generated reports stay in the local workspace and are excluded from Git. A fresh clone needs those private inputs before rebuilding the saved campaign; the result links below refer to local artifacts, not files published on GitHub.

ShippyPro only: discover public shipping signals, score 100 companies against its ICP, select 50 contacts, enrich their professional details, and prepare four researched messages per contact.

The original source-first workflow, scoring rules, connected web/Clay runner and review dashboard are restored. SQLite persistence is retained. There is no active multi-campaign framework, direct-provider key setup or deployment scheduler.

## Run locally

Python 3.10+; no pip packages required:

```sh
./run_campaign.sh build --campaign
python3 src/outbound_engine.py serve --port 8765
```

Open **http://127.0.0.1:8765**. Review contacts, edit drafts and save notes directly to the existing audit database. Press Ctrl+C to stop the server.

To rebuild only the source-based account assessment and lead database:

```sh
python3 src/pipeline.py build
```

These commands rebuild the real saved receipts. Fresh collection still uses the original connected web/Clay workflow in this agent session; it is not an unattended scraper. See [RUNBOOK.md](RUNBOOK.md). No messages are sent: this remains an independent ghost audit.

## Database and results

- [Two-table lead database](results/leads.sqlite3): `raw_leads` holds scraped/source records; `usable_leads` holds selected company/contact details, original fit/intent scores, evidence and draft snapshots. Prior snapshots are retained. Emails are provider-returned, not independently deliverability-verified; those rows remain `needs_refresh`.
- [Original campaign dashboard](results/outbound_v1/campaign.html): 50 contacts and 200 drafts; also works directly from disk with browser-local edits.
- [100 scored companies](results/signal_first_v3/accounts_100_scored.csv).
- [50 enriched contacts](results/signal_first_v3/top_50_enriched.csv).
- [Raw database export](results/signal_first_v3/raw_leads.csv) and [enriched database export](results/signal_first_v3/usable_leads.csv).
- `results/outbound_v1/campaign.sqlite3`: original review, notes, draft edits and audit history. Builds preserve manual edits.

The old reusable-engine database is preserved for recovery but is no longer used by this workflow. Fixed compatibility IDs in the lead schema preserve existing records; no campaign selection is required. The removed framework, provider adapters, deployment bundle and documentation are recoverable under `archive/pre-shippypro-simplification/`.

[Workflow details](RUNBOOK.md) · [Research, messages and review commands](OUTBOUND_RUNBOOK.md) · [Lead SQL schema](src/simple_lead_schema.sql)

```sh
python3 -m unittest discover -s tests -v
node tests/outbound_dashboard_state.cjs
```
