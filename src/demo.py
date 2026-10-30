"""Synthetic demo workspace: five sample accounts, the real engine, a throwaway database."""
import json
from pathlib import Path
import outbound_engine as engine
import linkedin_copy
from lead_store import LeadStore
from shippypro_db import SCOPE, fingerprint

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'sample_data/demo_accounts.json'
OUT = ROOT / 'results/demo'
CAMPAIGN_DB = OUT / 'campaign.sqlite3'
LEADS_DB = OUT / 'leads.sqlite3'
FIT = ['fit_geography', 'fit_parcels', 'fit_vertical', 'fit_scale', 'fit_complexity']


def config():
    return dict(engine.read(engine.CFG), campaign_id='shippypro-demo', name='ShippyPro GTM engine (synthetic demo)',
                mode='demo', primary_source=str(SAMPLE.relative_to(ROOT)))


def research(r, a):
    return {'research_status': 'public_business_context_found', 'researched_at': r['event_date'],
            'observed_company_event': r['signal'], 'event_date': r['event_date'], 'company_source': r['source_url'],
            'company_receipt': 'sample_data/demo_accounts.json', 'person_public_fact': a['personal_fact'],
            'person_fact_status': 'synthetic', 'person_sources': [], 'search_receipt': 'sample_data/demo_accounts.json',
            'reported_role': r['job_title'], 'persona_hypothesis': a['persona'], 'need_hypothesis': a['question'],
            'hypothesis_status': 'synthetic demo hypothesis', 'suggested_diagnostic': a['diagnostic'],
            'proposed_measure': a['metric'], 'product_capability_source': engine.FEATURES[a['feature']]['url'],
            'review_flags': [] if r['work_email'] else ['Work email missing in the sample; shows the email-gap state.'],
            'signal_caveat': r['signal_caveat'], 'email_status': r['email_status'], 'email_domain_status': 'synthetic'}


def build(out=OUT):
    """Recreate both demo databases from sample_data/. Never touches results/ outside results/demo."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ['campaign.sqlite3', 'leads.sqlite3']:
        for suffix in ['', '-wal', '-shm']:
            (out / (name + suffix)).unlink(missing_ok=True)
    rows, cfg = engine.read(SAMPLE), config()
    for r in rows:
        r['icp_score'] = sum(r[k] for k in FIT)
    c = engine.connect(out / 'campaign.sqlite3')
    engine.init(c)
    with c:
        for r in rows:
            a, t = r['angle'], engine.now()
            cid = engine.stable(cfg['campaign_id'] + '|' + r['domain'] + '|' + engine.profile_key(r['linkedin']))
            rr = research(r, a)
            linkedin = linkedin_copy.drafts(cid, r, a, r['linkedin_hook'], engine.FEATURES[a['feature']], cfg['official_demo_url'])
            c.execute('INSERT INTO contacts(id,domain,rank,name,company,email,linkedin,title,research_json,linkedin_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (cid, r['domain'], r['rank'], r['decision_maker'], r['company'], r['work_email'], r['linkedin'], r['job_title'], json.dumps(rr), json.dumps(linkedin), t, t))
            engine.event(c, cid, 'research_recorded', {'mode': 'demo', 'source': rr['search_receipt']}, eid='research-' + cid)
            for m in engine.drafts(r, a, cfg):
                mid, h = cid + '-' + str(m['step']), engine.stable(m['subject'] + '\n' + m['body'])
                c.execute('INSERT INTO messages(id,contact_id,step,day_offset,subject,body,evidence_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (mid, cid, m['step'], m['day_offset'], m['subject'], m['body'], json.dumps(m['evidence']), h, t, t))
                engine.event(c, cid, 'draft_created', {'step': m['step'], 'content_hash': h}, mid, eid='draft-' + mid)
    c.close()
    store = LeadStore(out / 'leads.sqlite3')
    for r in rows:
        scored = {k: v for k, v in r.items() if k not in ('angle', 'linkedin_hook')}
        raw = store.record(SCOPE, 'demo:' + r['domain'], 'candidate', scored, r['source_url'], r['company'], r['domain'])
        store.mark(SCOPE, raw['id'], r['qualification'], {'icp_score': r['icp_score'], 'signal_strength': r['signal_strength']})
        store.promote(SCOPE, {
            'raw_lead_id': raw['id'], 'account_id': r['domain'], 'contact_id': 'p_' + fingerprint(r['linkedin'])[:24],
            'config_version': 1, 'input_version': fingerprint(scored), 'tier': r['qualification'],
            'company_name': r['company'], 'website': r['domain'], 'industry': r['sector'], 'country': r['country'],
            'employee_count': r['employee_count'], 'intent_signal': r['signal'], 'intent_source_url': r['source_url'],
            'intent_event_at': r['event_date'], 'intent_score': r['signal_strength'], 'fit_score': r['icp_score'],
            'qualification_reason': 'Synthetic demo record scored with the ShippyPro ICP rules.',
            'contact_name': r['decision_maker'], 'contact_title': r['job_title'], 'linkedin_url': r['linkedin'],
            'email': r['work_email'] or None, 'email_status': 'unverified' if r['work_email'] else 'missing',
            'refresh_due_at': engine.now(), 'status': 'needs_refresh'})
    return {'campaign_db': str(out / 'campaign.sqlite3'), 'leads_db': str(out / 'leads.sqlite3'), 'accounts': len(rows)}


def state(db=CAMPAIGN_DB):
    return dict(engine.state(db), campaign=config())


def page(data):
    return engine.html_page(data).replace('Real prospects and public research.', 'Synthetic demo data from sample_data/.')


def serve(port):
    """Review server over the demo database, rebuilt fresh on every start."""
    print(json.dumps(build(), indent=2), flush=True)
    engine.serve(port, CAMPAIGN_DB, load=state, page=page, exports=False, label='ShippyPro demo (synthetic data)')


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
