"""Zero-dependency MCP server (stdio JSON-RPC) over the lead and campaign databases.

Tools: get_top_scored_accounts, inspect_account_evidence, update_draft_status.
Writes go through outbound_engine.update, so revisions, audit events and the
edited-draft protection apply exactly as they do in the review dashboard.
Run with --demo to use the synthetic sample_data/ workspace.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buying_committee
import demo
import outbound_engine as engine
from shippypro_db import DB as LEADS_DB, SCOPE

DEMO = '--demo' in sys.argv
if DEMO and not demo.CAMPAIGN_DB.exists():
    demo.build()
CAMPAIGN = demo.CAMPAIGN_DB if DEMO else engine.DB
LEADS = demo.LEADS_DB if DEMO else LEADS_DB
FIT = ['fit_geography', 'fit_parcels', 'fit_vertical', 'fit_scale', 'fit_complexity']


def query(path, sql, args=()):
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, args)]
    finally:
        db.close()


def campaign_contacts():
    return {r['domain']: r for r in query(CAMPAIGN, 'SELECT id,domain,name,title,review_status FROM contacts')}


def get_top_scored_accounts(min_score=0, shipping_signal='', country='', limit=10):
    """Selected accounts by ICP fit, then signal strength. shipping_signal matches signal and source text."""
    like = f'%{shipping_signal}%'
    rows = query(LEADS, '''SELECT u.company_name,u.website,u.country,u.industry,u.fit_score,u.intent_score,u.intent_signal,
        u.intent_event_at,u.intent_source_url,u.contact_name,u.contact_title,u.email_status,u.status
        FROM usable_leads u JOIN raw_leads r ON r.id=u.raw_lead_id AND r.campaign_id=u.campaign_id
        WHERE u.campaign_id=? AND u.status!='excluded' AND u.fit_score>=?
          AND (?='' OR u.intent_signal LIKE ? OR r.raw_data_json LIKE ?) AND (?='' OR u.country LIKE ?)
        ORDER BY u.fit_score DESC,u.intent_score DESC LIMIT ?''',
                 (SCOPE, min_score, shipping_signal, like, like, country, f'%{country}%', max(1, min(int(limit), 100))))
    contacts = campaign_contacts()
    for r in rows:
        c = contacts.get(r['website'], {})
        r.update(contact_id=c.get('id'), review_status=c.get('review_status'), committee_role=buying_committee.classify(r['contact_title']))
    return rows


def inspect_account_evidence(company_name):
    """Public signal, fit breakdown, research flags and current drafts for one account (any of the scored accounts)."""
    # raw_leads keeps every source snapshot; the latest one per domain is current.
    raw = query(LEADS, '''SELECT raw_data_json,status FROM raw_leads WHERE id IN (SELECT max(id) FROM raw_leads
        WHERE campaign_id=? AND (company_name LIKE ? OR website LIKE ?) GROUP BY website)''',
                (SCOPE, f'%{company_name}%', f'%{company_name}%'))
    if not raw:
        return {'error': f'No scored account matches {company_name!r}'}
    if len(raw) > 1:
        return {'error': 'Several accounts match; be more specific', 'matches': [json.loads(r['raw_data_json'])['company'] for r in raw]}
    a = json.loads(raw[0]['raw_data_json'])
    result = {'company': a['company'], 'domain': a['domain'], 'qualification': raw[0]['status'],
              'signal': {k: a.get(k) for k in ['signal', 'event_date', 'source_title', 'source_url', 'signal_class', 'signal_caveat']},
              'fit': {k: a.get(k) for k in FIT + ['icp_score', 'signal_strength', 'priority_score', 'scale_basis', 'exclusion_reason']}}
    contact = campaign_contacts().get(a['domain'])
    if contact:
        state = next(c for c in engine.state(CAMPAIGN)['contacts'] if c['id'] == contact['id'])
        r = state['research']
        result['contact'] = {'contact_id': state['id'], 'name': state['name'], 'title': state['title'], 'committee': state['committee'],
                             'review_status': state['review_status'], 'review_flags': r['review_flags'],
                             'need_hypothesis': r['need_hypothesis'], 'diagnostic': r['suggested_diagnostic'], 'measure': r['proposed_measure']}
        result['email_drafts'] = [{k: m[k] for k in ['step', 'day_offset', 'subject', 'body', 'review_status', 'revision', 'edited']} for m in state['messages']]
        result['linkedin_drafts'] = [{k: m[k] for k in ['step', 'subject', 'body', 'review_status', 'revision']} for m in state['linkedin_messages']]
    return result


def update_draft_status(contact_id, touch_number, new_copy='', status='', subject='', channel='email'):
    """Rewrite one touch and/or set the contact's review status. Nothing is ever sent."""
    cid = engine.resolve_contact(contact_id, CAMPAIGN)
    # Real workspace: refresh exports and the dashboard file like a dashboard save. Demo: database only.
    export = not DEMO
    contact = next(c for c in engine.state(CAMPAIGN)['contacts'] if c['id'] == cid)
    if new_copy:
        if channel == 'linkedin':
            m = next(m for m in contact['linkedin_messages'] if m['step'] == int(touch_number))
            engine.update(CAMPAIGN, dict(action='edit_linkedin', contact_id=cid, message_id=m['id'], revision=m['revision'], body=new_copy), export)
        else:
            m = next(m for m in contact['messages'] if m['step'] == int(touch_number))
            engine.update(CAMPAIGN, dict(action='edit_message', contact_id=cid, message_id=m['id'], revision=m['revision'],
                                         subject=subject or m['subject'], body=new_copy), export)
    if status:
        engine.update(CAMPAIGN, dict(action='review', contact_id=cid, status=status), export)
    after = next(c for c in engine.state(CAMPAIGN)['contacts'] if c['id'] == cid)
    m = next(m for m in after['linkedin_messages' if channel == 'linkedin' else 'messages'] if m['step'] == int(touch_number))
    return {'contact_id': cid, 'company': after['company'], 'review_status': after['review_status'],
            'touch': {k: m.get(k) for k in ['step', 'subject', 'body', 'review_status', 'revision', 'edited']}, 'sent': False}


TOOLS = {
    'get_top_scored_accounts': (get_top_scored_accounts, {
        'min_score': {'type': 'number', 'description': 'Minimum ICP fit score, 0-100'},
        'shipping_signal': {'type': 'string', 'description': 'Text to match in the public signal, e.g. "DHL", "returns", "launch"'},
        'country': {'type': 'string', 'description': 'Country name filter, e.g. "Germany"'},
        'limit': {'type': 'integer', 'description': 'Max rows, default 10'}}, []),
    'inspect_account_evidence': (inspect_account_evidence, {
        'company_name': {'type': 'string', 'description': 'Company name or domain (partial match)'}}, ['company_name']),
    'update_draft_status': (update_draft_status, {
        'contact_id': {'type': 'string', 'description': 'Campaign contact ID, company domain or contact name'},
        'touch_number': {'type': 'integer', 'description': 'Sequence step, 1-4'},
        'new_copy': {'type': 'string', 'description': 'Replacement message body; omit to change status only'},
        'subject': {'type': 'string', 'description': 'Email subject; defaults to the current subject'},
        'status': {'type': 'string', 'enum': ['reviewed', 'needs_revision', 'unreviewed'], 'description': 'Review status for the contact (applies to all its touches)'},
        'channel': {'type': 'string', 'enum': ['email', 'linkedin']}}, ['contact_id', 'touch_number']),
}


def handle(msg):
    method, params = msg.get('method'), msg.get('params') or {}
    if method == 'initialize':
        return {'protocolVersion': params.get('protocolVersion', '2025-06-18'), 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'shippypro-gtm' + ('-demo' if DEMO else ''), 'version': '1.0.0'}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [{'name': n, 'description': f.__doc__.strip(), 'inputSchema': {'type': 'object', 'properties': p, 'required': r}}
                          for n, (f, p, r) in TOOLS.items()]}
    if method == 'tools/call':
        fn = TOOLS[params['name']][0]
        try:
            text, error = json.dumps(fn(**params.get('arguments', {})), ensure_ascii=False, indent=1, default=str), False
        except (ValueError, KeyError, TypeError, StopIteration, sqlite3.Error) as e:
            text, error = f'{type(e).__name__}: {e}', True
        return {'content': [{'type': 'text', 'text': text}], 'isError': error}
    raise LookupError(method)


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        if 'id' not in msg:
            continue  # notifications need no reply
        try:
            reply = {'jsonrpc': '2.0', 'id': msg['id'], 'result': handle(msg)}
        except LookupError as e:
            reply = {'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32601, 'message': f'Method not found: {e}'}}
        sys.stdout.write(json.dumps(reply) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()
