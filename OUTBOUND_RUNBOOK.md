# ShippyPro independent campaign audit

This is an independent ghost audit using real prospect records and public business information. It is proposed ShippyPro campaign copy, not ShippyPro's actual campaign or an authorised sales effort. No mailbox, sender identity, external sequence, tracking pixel, live booking attribution or message transport is connected. Nothing has been sent. The system does not claim access to ShippyPro's internal CRM, sales workflow or conversion data.

## Open and use the campaign

Open `results/outbound_v1/campaign.html` in a normal browser. Select any contact to see the observed event, professional research, source URLs, role-based hypothesis, proposed diagnostic, review flags and all four messages. Search by person, company or role. The proposed touches are day 0, 4, 9 and 16 in business days after a hypothetical activation; no activation date or deliveries exist.

The file works directly without a server. Draft edits, review statuses and notes persist in that browser's local storage. “Mark reviewed for audit” does not authorise sending. Use **Export current messages CSV** for the current browser-edited copy and **Export review backup** to preserve notes, edits and review decisions in a portable JSON file. Header CSV links contain the baseline database export. Browser-local changes do not silently update SQLite.

If your browser blocks local storage, the page becomes read-only; use the CLI below. The coding environment blocks binding a local server port. The optional Python server is implemented for use in your own terminal but was not run successfully in this environment. UI state transitions were checked with a JavaScript DOM/state harness; visual browser rendering was not verified because the in-app browser execution tool was unavailable.

## What is included

- `campaign_contacts_50.csv`: one row per contact, all four messages, research and status fields.
- `campaign_messages_200.csv`: one row per touch; subjects, bodies, offsets and source URLs. Sent dates and provider IDs remain blank.
- `research_50.json`: observed facts, attributable professional context, hypotheses and research caveats.
- `campaign.sqlite3`: durable local campaign, draft revisions and audit-event history.
- `copy_qa.json`: per-message word counts and checks for unsupported claims or unresolved placeholders.
- `raw/`: fresh public research for all 50 people, product verification, a three-contact Clay research comparison and targeted recovery receipts.
- `config/outbound/angles.tsv`: 50 individually authored message angles, diagnostics and proposed measures.
- `context/outbound/`: audience, product evidence and copy constraints.

The campaign preserves 44 provider-returned work emails and six missing emails. Fresh public research returned professional business context for 49 contacts; NFI's Eddie Shelton remains provider-context-only after targeted public searches. Public context is not proof of current buying authority. Twenty-three contacts carry an email, scope, role or product-fit flag. The remaining records still require normal operational verification before any real campaign.

## Message approach

Touch 1 connects an observed company change or attributable professional activity to a specific operational question. Touch 2 gives a concrete workflow check and a proposed measure. Touch 3 outlines a bounded ShippyPro product scenario and links to its public demo-request form. Touch 4 closes the loop without pressure. The copy mentions ShippyPro transparently and asks about potential needs; it does not claim that a prospect is struggling or that an internal audit has already occurred. The public demo link is not a connected calendar.

No guaranteed savings, false familiarity, invented customer evidence or unsupported integration promises are used. Carrier coverage, product-specific requirements and the actual buyer's responsibility must be checked. Cold-chain, freight, furniture and appliance delivery are not treated as automatically covered by a parcel-shipping product.

Useful findings include SHEIN's contact having a Latin America/Caribbean remit rather than verified ownership of the Indiana project; Arvato's contact having a Turkey/automotive background without established ownership of the Spanish beauty hub; conflicting seniority descriptions for Bergzeit and Groupe BLONDEL; and unresolved exact seniority for the Levi Strauss contact. The audit retains these findings instead of presenting all 50 as ready-to-send buyers.

## Rebuild and review locally

```sh
python3 src/outbound_engine.py build
python3 src/outbound_engine.py summary
python3 src/outbound_engine.py review --contact refybeauty.com --status reviewed
python3 src/outbound_engine.py note --contact refybeauty.com --text 'Confirm the relevant delivery-workflow owner.'
python3 src/outbound_engine.py import-review --file /path/to/shippypro-review-backup.json
```

Rebuilds reuse saved research and preserve edited drafts, notes and review history. A regenerated draft or changed evidence invalidates the affected review. Import validates campaign/contact identity and draft hashes, stages all changes on a database copy, and refuses conflicting drafts without partially applying the backup. Re-importing the same backup is idempotent.

To rebuild the original account list and the campaign together:

```sh
python3 src/pipeline.py build --campaign
```

Optional server on your own machine:

```sh
python3 src/outbound_engine.py serve --port 8765
```

Then open `http://127.0.0.1:8765`. In this mode edits persist directly to SQLite. The server binds only to loopback and accepts audit review, notes and draft edits. There is no send, simulated reply or activation operation.

## Checks

```sh
python3 -m unittest discover -s tests -v
node tests/outbound_dashboard_state.cjs
```

Checks cover the 50-by-4 population, no-send boundary, source lineage, role/scope flags, empty emails, stable IDs, edit persistence, review invalidation, duplicate requests, stale revisions, atomic backup import, browser-storage reloads and current-message export. Tests mutate only temporary databases and in-memory browser storage.

Provider costs were not exposed. The live collection used connected Clay/web tools; no completed Deepline Play or exact credit receipt is claimed. No third-party CRM or outreach platform was modified.
