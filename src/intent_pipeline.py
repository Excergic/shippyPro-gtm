"""Strict purchase-intent gate. Never use operating fit as intent evidence."""
from __future__ import annotations
import argparse, csv, html, json, re, sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from icp_pipeline import accepted_contact

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/intent_v2'
RAW=OUT/'raw'
ALLOWED={'open_rfp','explicit_vendor_evaluation','announced_replacement','active_named_shipping_software_implementation'}
FIELDS=['rank','company_name','company_domain','supported_intent_score','intent_qualified','status','evidence_category',
        'observed_signal','source_url','publication_date','opportunity_state','missing_evidence','next_fact_needed',
        'research_queries','research_receipt','result_sources','as_of']
CONTACT_FIELDS=['company_domain','name','title','linkedin_url','role_evidence_urls','budget_authority']

def read(path,default=None):return json.loads(path.read_text()) if path.exists() else default

def source_text(result):
    return '\n'.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')

def normalized(text):
    text=re.sub(r'(?m)^L\d+:\s?','',text)
    return re.sub(r'\s+',' ',text).strip()

def qualify(claim,as_of,source=None):
    """Return points and every failed gate; booleans are explicit analyst decisions."""
    reasons=[]
    if claim.get('signal_class') not in ALLOWED:reasons.append('Unaccepted signal class')
    for key in ['identity_verified','icp_verified','parcel_software_scope','buyer_attributed','open_opportunity_verified']:
        if claim.get(key) is not True:reasons.append('Missing '+key)
    if claim.get('opportunity_state') not in ['open_evaluation','open_rfp','active_implementation_open_to_vendors']:
        reasons.append('Open relevant purchasing opportunity not established')
    if claim.get('already_selected_vendor') is True:reasons.append('Vendor already selected; new purchasing opening unproven')
    try:pub=date.fromisoformat(claim['publication_date'])
    except (KeyError,TypeError,ValueError):pub=None;reasons.append('Missing attributable publication date')
    deadline=None
    if claim.get('deadline'):
        try:deadline=date.fromisoformat(claim['deadline'])
        except ValueError:reasons.append('Invalid deadline')
        if deadline and deadline<as_of:reasons.append('Opportunity expired')
    if pub and pub>as_of:reasons.append('Future publication')
    if pub and (as_of-pub).days>180 and not(deadline and deadline>=as_of):reasons.append('Stale source and no open deadline')
    try:observed=date.fromisoformat(claim['status_verified_at'])
    except (KeyError,TypeError,ValueError):observed=None;reasons.append('Current status not verified')
    if observed and not 0<=(as_of-observed).days<=14:reasons.append('Status observation stale or future')
    if source is None:reasons.append('Source was not fetched')
    else:
        body=source_text(source.get('result',{}))
        if source.get('result',{}).get('isError') or 'Content type:' not in body or not re.search(r'Total lines: [1-9]',body):
            reasons.append('Fetched page unavailable or unreadable')
        if source.get('url') != claim.get('source_url'):reasons.append('Source receipt URL mismatch')
        for key in ['project_quote','open_status_quote']:
            quote=claim.get(key,'')
            if not quote or normalized(quote) not in normalized(body):reasons.append('Unsupported '+key)
    if not claim.get('buyer_or_owner'):reasons.append('No attributable buyer or project owner')
    if reasons:return 0,reasons
    base={'open_rfp':90,'explicit_vendor_evaluation':85,'announced_replacement':80,'active_named_shipping_software_implementation':70}[claim['signal_class']]
    return min(100,base+(10 if pub and (as_of-pub).days<=30 else 5)),[]

def write_csv(path,rows,fields):
    def safe(v):return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows({k:safe(v) for k,v in r.items()} for r in rows)
    tmp.replace(path)

def build():
    contract=read(ROOT/'config/intent_contract.json');as_of=date.fromisoformat(contract['as_of'])
    accounts=read(ROOT/'config/accounts.json');reviews=read(ROOT/'config/intent_reviews.json',{})
    assert len(accounts)==100 and len({c['domain'] for c in accounts})==100
    watch={r['company_domain']:r for r in reviews.get('watchlist',[])}
    rejected={r['company_domain']:r for r in reviews.get('rejections',[])}
    claims={c['company_domain']:c for c in reviews.get('qualified_claims',[])}
    rows=[];sources=[];claims_audit=[]
    for c in accounts:
        domain=c['domain'];path=RAW/('research-'+domain+'.json');receipt=read(path,{})
        result=receipt.get('result',{});text=source_text(result)
        urls=list(dict.fromkeys(re.findall(r'\((https?://[^\s]+)\)\s*\n',text)))
        outcome='provider_error' if result.get('isError') or not receipt else 'retrieved' if urls else 'no_results'
        source=watch.get(domain) or rejected.get(domain) or {}
        points=0;reasons=[];claim=claims.get(domain)
        if claim:
            receipt_path=claim.get('source_fetch_receipt')
            fetched=read(ROOT/receipt_path,None) if isinstance(receipt_path,str) and receipt_path else None
            points,reasons=qualify(claim,as_of,fetched)
        if not reasons and not points:reasons=[source.get('why_not_qualified','No current named parcel-software evaluation, replacement, open RFP or accessible implementation purchase established in bounded public searches.')]
        if outcome=='provider_error':reasons.append('Research route failed; not a provider no-match')
        row={'company_name':c['name'],'company_domain':domain,'supported_intent_score':points,'intent_qualified':bool(points),
          'status':'qualified' if points else 'research_error' if outcome=='provider_error' else 'needs_confirmation' if domain in watch else 'insufficient_public_evidence',
          'evidence_category':claim.get('signal_class') if points else source.get('classification','No qualifying public purchasing evidence'),
          'observed_signal':claim.get('summary','') if points else source.get('signal',''),
          'source_url':claim.get('source_url','') if points else source.get('source_url',''),
          'publication_date':claim.get('publication_date','') if claim else '',
          'opportunity_state':claim.get('opportunity_state','') if points else 'unverified',
          'missing_evidence':'; '.join(reasons),
          'next_fact_needed':source.get('next_fact_needed','Buyer-attributed evidence naming the parcel-software project, its current purchasing stage, date and owner.'),
          'research_queries':' | '.join(receipt.get('queries',[])),
          'research_receipt':str(path.relative_to(ROOT)) if receipt else '',
          'result_sources':' | '.join(urls),'as_of':as_of.isoformat()}
        rows.append(row)
        sources.extend({'company_domain':domain,'source_url':u,'acquisition':'search_index; not automatically verified','receipt':row['research_receipt']} for u in urls)
        claims_audit.append({'company_domain':domain,'retrieval_status':outcome,'gate_failures':reasons,'accepted':bool(points)})
    rows.sort(key=lambda r:(-r['supported_intent_score'],r['company_domain']))
    for i,r in enumerate(rows,1):r['rank']=i
    qualified=[r for r in rows if r['intent_qualified']][:50]
    # Historical contacts are usable only after the account intent gate passes.
    qdomains={r['company_domain'] for r in qualified};contacts=[]
    old=ROOT/'results/icp_v1/decision_makers.csv'
    if old.exists():
        with old.open() as f:
            for c in csv.DictReader(f):
                try:observed=date.fromisoformat(c.get('observed_at',''))
                except ValueError:continue
                if c['company_domain'] in qdomains and 0<=(as_of-observed).days<=30:contacts.append(c)
    for path in RAW.glob('people-*.json'):
        receipt=read(path,{})
        for c in receipt.get('contacts',[]):
            domain=c.get('companyIdentifier') or c.get('domain')
            if domain not in qdomains or not accepted_contact(c):continue
            contacts.append({'company_domain':domain,'name':c['name'],'title':c['latest_experience_title'],
                'linkedin_url':c['url'],'role_evidence_urls':c['url'],'budget_authority':'unverified'})
    contacts=list({(c['company_domain'],c['linkedin_url']):c for c in contacts}.values())
    OUT.mkdir(parents=True,exist_ok=True)
    for base in [OUT,ROOT/'results']:
        write_csv(base/'accounts_100_scored.csv',rows,FIELDS)
        write_csv(base/'top_50_qualified.csv',qualified,FIELDS)
        write_csv(base/'decision_makers.csv',contacts,CONTACT_FIELDS)
    write_csv(OUT/'watchlist.csv',[r for r in rows if r['status']=='needs_confirmation'],FIELDS)
    write_csv(ROOT/'results/account_intent_audit.csv',rows,FIELDS)
    write_csv(ROOT/'results/contact_gaps.csv',[{'company_name':r['company_name'],'company_domain':r['company_domain'],
      'reason':'Account failed intent gate; contact eligibility withheld, not a claim that contacts do not exist.'} for r in rows if not r['intent_qualified']],['company_name','company_domain','reason'])
    write_csv(OUT/'source_coverage.csv',claims_audit,['company_domain','retrieval_status','gate_failures','accepted'])
    for base in [OUT,ROOT/'results']:(base/'source_ledger.json').write_text(json.dumps(sources,indent=2))
    summary={'contract_version':2,'as_of':as_of.isoformat(),'accounts_screened':len(rows),
      'accounts_with_research_receipts':sum(bool(r['research_receipt']) for r in rows),
      'public_search_queries':sum(len(read(RAW/('research-'+c['domain']+'.json'),{}).get('queries',[])) for c in accounts),
      'source_fetch_attempts':len(list(RAW.glob('fetch-*.json'))),
      'readable_source_pages':sum(bool(re.search(r'Total lines: [1-9]',source_text(read(p,{}).get('result',{})))) for p in RAW.glob('fetch-*.json')),
      'intent_qualified_accounts':len(qualified),'target_qualified_accounts':50,'qualification_shortfall':50-len(qualified),
      'watchlist_accounts':sum(r['status']=='needs_confirmation' for r in rows),'eligible_contacts':len(contacts),
      'research_errors':sum(r['status']=='research_error' for r in rows),
      'status':'target_met' if len(qualified)==50 else 'target_not_met',
      'first_party_shippypro_data_accessed':False,
      'meaning_of_zero':'No accepted purchase-intent evidence; not a claim that the company has no intent.',
      'limits':['Public search is not exhaustive.','Search snippets do not pass qualification without a fetched attributable source.',
      'Prior fit-based accounts and contacts are archived in results/icp_v1; they are not intent-qualified.',
      'No first-party CRM, trial telemetry, website engagement or identified intent feed was accessed.',
      'Live retrieval requires connected agent tools. No recurring schedule is deployed.']}
    for base in [OUT,ROOT/'results']:(base/'summary.json').write_text(json.dumps(summary,indent=2))
    for base in [OUT,ROOT/'results']:(base/'accounts.json').write_text(json.dumps(rows,indent=2))
    (OUT/'claim_decisions.json').write_text(json.dumps(claims_audit,indent=2))
    display=[r for r in rows if r['status']=='needs_confirmation']
    table=''.join('<tr><td>'+html.escape(r['company_name'])+'</td><td>'+html.escape(r['observed_signal'])+'</td><td>'+html.escape(r['missing_evidence'])+'</td><td><a href="'+html.escape(r['source_url'],quote=True)+'">Evidence</a></td></tr>' for r in display)
    report='<!doctype html><meta charset="utf-8"><title>ShippyPro intent qualification</title><style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px;color:#182332}table{border-collapse:collapse}td,th{padding:14px;border-bottom:1px solid #ddd;text-align:left}a{color:#2258bb}.metrics{font-size:22px;padding:20px;background:#eef3f8}</style><h1>ShippyPro — intent qualification</h1><p>Public-source audit as of '+as_of.isoformat()+'.</p><p class="metrics">100 accounts screened · '+str(len(qualified))+' intent-qualified · '+str(50-len(qualified))+' short of the requested 50</p><p><strong>The requested outcome has not been achieved.</strong> Only accounts with evidence of an open relevant purchasing project can pass. Existing shipping operations, growth and completed rollouts earn no intent points.</p><p>A score of zero means evidence was not established. It does not mean the company has no intent.</p><p><a href="accounts_100_scored.csv">100-account audit</a> · <a href="top_50_qualified.csv">Qualified accounts</a> · <a href="decision_makers.csv">Eligible contacts</a></p><h2>Watchlist — confirmation needed</h2><p>These records are research leads, not qualified buying opportunities.</p><table><tr><th>Company</th><th>Observed evidence</th><th>Why it does not pass</th><th>Source</th></tr>'+table+'</table><h2>Access needed to close the gap</h2><p>A buyer-confirmed active-project feed or authorized ShippyPro CRM/product signals can establish intent that public pages do not reveal. A live job vacancy alone cannot establish an open vendor decision.</p><p>Earlier fit-based results are preserved under results/icp_v1. They should not be used as an intent list.</p>'
    for base in [OUT,ROOT/'results']:(base/'report.html').write_text(report)
    db=sqlite3.connect(ROOT/'results/shippypro.sqlite3')
    for name,data in [('accounts',rows),('contacts',contacts)]:
        db.execute('CREATE TABLE IF NOT EXISTS '+name+' (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('DELETE FROM '+name)
        for item in data:db.execute('INSERT INTO '+name+' VALUES (?,?)',(item['company_domain']+'|'+item.get('linkedin_url',''),json.dumps(item)))
    db.commit();db.close()
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['build']);parser.parse_args();build()
