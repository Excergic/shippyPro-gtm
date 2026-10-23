# Run and inspect the workflow

The order is **public signal discovery → identify company → ICP assessment → select 50 → company and person enrichment**. The live collection used connected web search and Clay. Deepline's CLI could not reach its service; this is not a completed Deepline Play and no credit-cost receipt is available.

The completed dataset is in `results/signal_first_v3/`. Root-level exports point to this version. Open `results/report.html` directly in a browser; search the table or use its CSV links. Import `top_50_enriched.csv` into your CRM or spreadsheet manually if desired. No CRM writes or outreach were performed.

## Files

- `top_50_enriched.csv`: 50 accounts, profiles, signals, dates, source URLs, score components and primary contacts.
- `decision_makers_50.csv`: one named primary contact and LinkedIn profile per selected company; email gaps and source receipts included.
- `additional_contacts.csv`: other relevant contacts at the same selected accounts.
- `accounts_100_scored.csv`: the complete source-discovered cohort, including failed ICP checks, stale or undated signals, and unresolved company profiles.
- `source_catalog.json`: 554 deduplicated source URLs from 32 discovery queries. The 100 companies were extracted from those events, not reused from the previous roster.
- `signal_candidates.json`: reviewed company/event/source manifest; `account_profiles.json`: company identity/profile resolution.
- `raw/`: live provider and search receipts, pagination, email contexts, failed lookups and recovery searches.
- `summary.json`: exact coverage. No spend estimate is substituted for unavailable billing data.

## What the scores mean

`icp_score` has five separate components: geography (20), parcel relevance (30), target vertical (20), company size proxy (20), and integration/operating complexity (10). An unresolved company profile receives a null score. A 70-point threshold, a dated signal no older than 365 days, an identified company profile and no exclusion/suppression are required for selection. Events older than 180 days receive fewer timing points. Missing event dates stay in review. The 50-person quota is not evidence of buying intent.

`priority_score` is an exploratory queue policy: 70% ICP score plus 30% normalized timing/signal points. Its source and fit components remain separately exported. No grade, conversion probability, causal lift or predictive validation is claimed. The model state is `exploratory_end_to_end`. No CRM won/lost or first-party intent data was available. Rules are in `src/signal_assessment.py`; the contract is `config/signal_first.json`.

Company profiles come from provider records; source-event descriptions are reviewed public evidence. Employee counts are provider-reported, not audited payroll. The same domain can resolve to a subsidiary, so company identity and scope require review. The current manifest resolves those selections in `account_profiles.json`. Parent/brand email-domain differences are explicitly marked for affiliation review. “Provider-returned” is not “deliverability-verified.” A completed empty provider result is a miss, not a guessed email pattern. Historical public email addresses are not promoted as current contacts.

## Rebuild the saved run

```sh
python3 src/pipeline.py build --campaign
python3 -m unittest discover -s tests -v
```

Python uses only the standard library and local receipts. It preserves all 100 source-discovered rows and regenerates the current report and CSVs. It never reads `config/accounts.json` as its discovery cohort.

## Make new live calls

`src/live_workflow.js` is an AsyncFunction body that uses connected tools in this agent environment. It is an agent-assisted workflow, not a standalone hosted daemon. Run it here with:

```javascript
const r = await tools.exec_command({cmd:'cat src/live_workflow.js', max_output_tokens:18000});
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const run = await new AsyncFunction('tools','options',r.output)(tools,{stage:'discover'});
text(run);
```

`discover` searches event-based query partitions and preserves new receipts. An agent then extracts/reviews the new company/event/date/domain manifest, resolves company profiles through Clay (retaining all pages), and updates the source/profile artifacts. This review step is required; a generic keyword hit is not a qualified account. Do not silently reuse an old roster as new discovery.

`build` regenerates outputs without provider calls. `enrich` searches people only at the 50 qualified accounts, applies employer/function gates through the Python export, requests primary work emails and retrieves contexts. Poll any in-progress task with `clay_get_task_context`, save the latest context, then rebuild. The runner preserves async pending states and does not claim completion while a lookup is pending. The observed Clay concurrency cap is two; the runner calls it sequentially. Changed titles or conflicting employers must be reviewed before accepting new contacts. Public-source and named-lookup recovery remain an agent step.

The live run delivered 50 profiles and 44 work emails. Six accounts have unresolved current primary emails after provider and public-search attempts: George at Asda, Tradeinn, EBIN NEW YORK, Levi Strauss, PHLUR, and Davinci Micro Fulfillment. Raw absence/recovery receipts are retained. Exact current work emails or an authorized second enrichment provider could close those gaps. There is no independent email-deliverability check, unattended schedule, or outbound execution.

## SQLite persistence

The original workflow also writes source records and enriched contact snapshots to `results/leads.sqlite3` (`raw_leads` and `usable_leads`). The original source-based scores are retained. The original audit database still stores draft revisions, notes and review history. No generic campaign framework or new provider API keys are required. Rebuilding receipts is not a fresh live collection or email verification.
