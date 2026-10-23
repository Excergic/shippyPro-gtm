"""Persist the original ShippyPro results in the existing two lead tables."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from lead_store import LeadStore

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'results/leads.sqlite3'
SCOPE = 'shippypro-audit'  # Fixed existing database label; no campaign selector.


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sync(campaign=None, db=DB, source=None):
    source = Path(source or ROOT / 'results/signal_first_v3')
    scored = json.loads((source / 'scored_accounts.json').read_text())
    selected = json.loads((source / 'selected_accounts.json').read_text())
    store = LeadStore(db)
    previous = store.rows(SCOPE, 'usable_leads')
    contacts = {p['domain']: p for p in (campaign or {}).get('contacts', [])}
    raw_ids = {}
    for row in scored:
        raw = store.record(SCOPE, 'shippypro-source:' + fingerprint(row), 'candidate', row,
                           row['source_url'], row['company'], row['domain'])
        store.mark(SCOPE, raw['id'], row['qualification'], {'icp_score': row.get('icp_score'),
                    'signal_strength': row.get('signal_strength'), 'exclusion_reason': row.get('exclusion_reason')})
        raw_ids[row['domain']] = raw['id']
    touched = []
    for row in selected:
        if not row.get('decision_maker') or not row.get('linkedin'):
            continue
        old = next((p for p in previous if p['website'] == row['domain'] and
                    (p.get('linkedin_url') or '').rstrip('/').casefold() == row['linkedin'].rstrip('/').casefold()), {})
        tracker = contacts.get(row['domain'], {})
        contact_id = old.get('contact_id') or ('p_' + fingerprint(row['linkedin'].rstrip('/').casefold())[:24])
        touched.append(contact_id)
        store.promote(SCOPE, {
            'raw_lead_id': raw_ids[row['domain']], 'account_id': old.get('account_id') or row['domain'],
            'contact_id': contact_id, 'config_version': 1, 'input_version': fingerprint(row),
            'tier': row['qualification'], 'company_name': row['company'], 'website': row['domain'],
            'industry': row.get('sector'), 'country': row.get('country'), 'employee_count': row.get('employee_count'),
            'intent_signal': row['signal'], 'intent_source_url': row['source_url'], 'intent_event_at': row.get('event_date'),
            'intent_score': row.get('signal_strength', 0), 'fit_score': row['icp_score'],
            'qualification_reason': 'Original ShippyPro ICP and signal rules; ' + row.get('signal_caveat', ''),
            'contact_name': row['decision_maker'], 'contact_title': row.get('job_title', ''),
            'linkedin_url': row['linkedin'], 'email': row.get('work_email') or None, 'phone': row.get('phone') or None,
            'email_status': 'unverified' if row.get('work_email') else 'missing',
            'enrichment_data_json': json.dumps({'research': tracker.get('research', {}),
                'email_status': row.get('email_status'), 'email_receipt': row.get('email_receipt'),
                'contact_receipt': row.get('contact_receipt'), 'review_status': tracker.get('review_status', 'unreviewed'),
                'note': tracker.get('note', ''), 'provenance': 'Saved ShippyPro source receipts; not a fresh live lookup'}),
            'messages_json': json.dumps(tracker.get('messages', [])), 'last_verified_at': None,
            'refresh_due_at': datetime.now(timezone.utc).isoformat(), 'status': 'needs_refresh'})
    # A company dropping out of the shortlist must not retain a stale usable row.
    with store.connection() as connection:
        for row in connection.execute('SELECT contact_id FROM usable_leads WHERE campaign_id=?', (SCOPE,)).fetchall():
            if row['contact_id'] not in touched:
                connection.execute("UPDATE usable_leads SET status='excluded' WHERE campaign_id=? AND contact_id=?", (SCOPE, row['contact_id']))
    store.export(SCOPE, source)
    return {'company': 'ShippyPro', 'database': str(store.path), 'source_accounts': len(scored),
            'selected_contacts': len(touched), 'sending_enabled': False,
            'note': 'Original source-based scores retained. Emails are provider-returned, not deliverability-verified.'}
