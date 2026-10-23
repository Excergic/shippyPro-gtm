"""Evidence-preserving ShippyPro account ranking. Python standard library only."""
from __future__ import annotations
import argparse, csv, hashlib, html, json, re, sqlite3, unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'deepline/data/shippypro-live/raw'
OUT = ROOT / 'results/icp_v1'
AS_OF = date.fromisoformat(json.loads((ROOT/'config/settings.json').read_text())['as_of'])
ALIASES = {
 'mango.com':['mangofashiongroup.com'], 'adidas.com':['adidas-group.com'],
 'asos.com':['asosplc.com'], 'cosstores.com':['cos.com','hmgroup.com'],
 'c-a.com':['c-and-a.com'], 'smcp.com':['maje.com'],
 'ovscorporate.it':['ovs.it'], 'birkenstock-group.com':['birkenstock.com'],
 'miroglio.com':['mirogliogroup.com'], 'kitsune.fr':['maisonkitsune.com'],
 'plt.shop':['prettylittlething.com'], 'debenhamsgroup.com':['debenhams.com'],
 'soliver-group.com':['soliver.com','soliver.de'], 'boardriders.eu':['boardriders.com'],
}
GROUPS = {'bershka.com':'Inditex','stradivarius.com':'Inditex','pullbear.com':'Inditex','zarahome.com':'Inditex',
 'smcp.com':'SMCP','sandro-paris.com':'SMCP','claudiepierlot.com':'SMCP',
 'ysl.com':'Kering','plt.shop':'Debenhams Group','debenhamsgroup.com':'Debenhams Group',
 'stoneisland.com':'Moncler Group','sunglasshut.com':'EssilorLuxottica',
 'cosstores.com':'H&M Group','salomon.com':'Amer Sports','kenzo.com':'LVMH','24s.com':'LVMH'}
OPERATING = re.compile(r'ship(?:ping|ped|ments)?|deliver(?:y|ies|ed)?|parcel|courier|fulfil|fulfill|logisti|spedizion|livraison|env[ií]o|liefer|warehouse|e-commerce|ecommerce',re.I)
CARRIERS = ['DHL','FedEx','UPS','DPD','GLS','Chronopost','Colissimo','Royal Mail','Evri','USPS','BRT','Correos','InPost','PostNL']
INTERNATIONAL = re.compile(r'international (?:shipping|delivery|orders)|ship(?:ping)? (?:worldwide|international)|deliver(?:y)? (?:worldwide|to.*countries)|cross.border|countries.*deliver|livraison.*international|Europe and International',re.I)
RETURNS = re.compile(r'return(?:s|ed)?|refund|reso|resi|retour|devolucion|rücksend',re.I)

def positive_international(text):
    for m in INTERNATIONAL.finditer(text):
        prefix=text[max(0,m.start()-75):m.start()]
        if not re.search(r'do not|don.t|cannot|no longer|not offer|not available|not support|only domestic',prefix,re.I):
            return True
    return False

def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def primary(url, domain):
    host=(urlparse(url).hostname or '').lower().removeprefix('www.')
    return any(host==d or host.endswith('.'+d) for d in [domain,*ALIASES.get(domain,[])])

def parse_sources(text):
    """Parse preserved web-tool receipts, retaining URL and source-local text."""
    result=[]
    for block in re.split(r'-{12,}',text):
        match=re.search(r'\((https?://[^\s]+)\)\s*\n',block)
        if not match: continue
        url=match.group(1)
        title=block[:match.start()].strip().replace('\n',' ')
        body=block[match.end():]
        body=re.sub(r'[^]*','',body)
        body=re.sub(r'\[wordlim:?\s*\d+\]','',body)
        result.append({'url':url,'title':title,'text':body.strip()})
    return result

def excerpt(text, pattern=OPERATING):
    # Quote at most 20 words per source claim.
    clean=re.sub(r'\s+',' ',text)
    match=pattern.search(clean)
    start=max(0,match.start()-50) if match else 0
    return ' '.join(clean[start:start+420].split()[:20])

def accepted_contact(c):
    title=c.get('latest_experience_title','')
    senior=bool(re.search(r'chief|\bcoo\b|\bcio\b|\bcto\b|director|directeur|directrice|direttore|head|vice president|\bvp\b|responsabile|leiter',title,re.I))
    function=bool(re.search(r'supply|logisti|fulfil|fulfill|e.?comm|operations|operating|digital|information|technology|omnichannel|distribution|transport|\bcoo\b|\bcio\b|\bcto\b|\bit director\b',title,re.I))
    bad=bool(re.search(r'store operations|retail head latam|showroom|assistant|consultant|former|past |intern\b|retired|digital marketing',title,re.I))
    return senior and function and not bad and bool(c.get('url','').startswith('https://www.linkedin.com/in/'))

def contact_rows():
    found={}
    for path in sorted(RAW.glob('contacts*.json')):
        d=read(path,{})
        observed=date.fromtimestamp(d['timestampMs']/1000) if d.get('timestampMs') else None
        if observed and not 0 <= (AS_OF-observed).days <= 30:
            continue
        contacts=d.get('contacts',[])
        if isinstance(contacts,dict):contacts=list(contacts.values())
        for c in contacts:
            if accepted_contact(c):
                c=dict(c,task_id=d.get('taskId'),observed_at=observed.isoformat() if observed else 'unknown',verification_status='provider_current_role; independently_reconfirm_before_outreach')
                found[(c.get('companyIdentifier') or c.get('domain'),c['url'])]=c
    for c in read(ROOT/'config/reviewed_contacts.json',[]):
        if not c.get('observed_at') or not 0 <= (AS_OF-date.fromisoformat(c['observed_at'])).days <= 30:
            continue
        if accepted_contact(c):
            c=dict(c,task_id=c['source_task_id'])
            found[(c['companyIdentifier'],c['url'])]=c
    return list(found.values())

def evaluate(c, event_reviews):
    domain=c['domain']; files=list(RAW.glob('web-'+domain+'*.json'))
    all_sources=[]
    for path in files:
        receipt=read(path)
        for s in parse_sources(receipt['response']):
            s['receipt']=str(path.relative_to(ROOT));s['is_primary']=primary(s['url'],domain)
            all_sources.append(s)
    unique={s['url']:s for s in all_sources};all_sources=list(unique.values())
    ops=[s for s in all_sources if s['is_primary'] and OPERATING.search(s['title']+' '+s['text'])
         and not re.search(r'privacy|careers|/jobs|modern.slavery|sustainab|impact.report|/test/',s['url'],re.I)
         and (re.search(r'shipping|delivery|returns|faq|logistics|livraison|spedizion|terms|conditions|client.service|customer.service',s['url'],re.I)
              or re.search(r'orders.{0,50}(?:shipped|delivered)|(?:ship|deliver).{0,30}(?:orders|countries|worldwide)|online.{0,20}(?:sales|store)|e.commerce.{0,30}(?:sales|warehouse)',s['text'],re.I))]
    # A policy, a logistics page, or a company report supplies parcel-operation evidence.
    ops.sort(key=lambda s: (bool(re.search(r'shipping|delivery|returns|logistics|livraison|spedizion',s['title'],re.I)),len(s['text'])),reverse=True)
    text=' '.join(s['title']+' '+s['text'] for s in ops)
    carrier_names=[x for x in CARRIERS if re.search(r'\b'+re.escape(x)+r'\b',text, re.I)]
    intl_sources=[s for s in ops if positive_international(s['text'])]
    intl=bool(intl_sources)
    return_sources=[s for s in ops if RETURNS.search(s['text'])]
    returns=bool(return_sources)
    carrier_sources=[s for s in ops if any(re.search(r'\b'+re.escape(x)+r'\b',s['text'],re.I) for x in carrier_names)]
    current_pain=[s for s in ops if re.search(r'currently experiencing delays|delays in processing returns',s['text'],re.I)]
    multicarrier=len(carrier_names)>=2
    parcel=bool(ops)
    size=c.get('size','');sizepoints=10 if size in ('51-200','201-500','501-1,000','1,001-5,000') else 6
    fit=15+10+sizepoints+(5 if parcel else 0)
    operational=min(30,(10 if intl else 0)+(10 if multicarrier else 0)+(10 if returns else 0)+(10 if current_pain else 0))
    events=[]
    for e in event_reviews.get(domain,[]):
        e=dict(e);event_day=date.fromisoformat(e['date']) if e.get('date') else None
        age=(AS_OF-event_day).days if event_day else None
        e['age_days']=age
        # A publication date is not automatically the date an event occurred.
        e['points']=e.get('weight',20)*(1 if age is not None and 0<=age<=180 else .5 if age is not None and 181<=age<=365 else 0)
        events.append(e)
    eventpoints=min(30,sum(max(e['points'] for e in events if e['type']==t) for t in set(e['type'] for e in events))) if events else 0
    score=fit+operational+eventpoints
    reason=[]
    if not parcel:reason.append('No first-party parcel-operation evidence accepted from searches')
    if not events:reason.append('No reviewed dated buying event; operating complexity is not purchase intent')
    if not intl:reason.append('International parcel scope unverified')
    row={'company_name':c['name'],'company_domain':domain,'country':c.get('country',''),'industry':c.get('industry',''),
      'company_size':size,'estimated_employees':c.get('employee_count'),'parent_group':GROUPS.get(domain,''),
      'fit_score':fit,'operational_score':operational,'recent_event_score':eventpoints,'score':score,
      'qualification_status':'ICP_qualified' if parcel else 'needs_evidence',
      'qualification_basis':'First-party search-index evidence of online shipping/logistics; size and sector from Clay' if parcel else '',
      'international_shipping_observed':intl,'multiple_carriers_observed':multicarrier,'returns_observed':returns,
      'international_evidence_urls':'; '.join(s['url'] for s in intl_sources),
      'returns_evidence_urls':'; '.join(s['url'] for s in return_sources),
      'carrier_evidence_urls':'; '.join(s['url'] for s in carrier_sources),
      'current_shipping_returns_pain_observed':bool(current_pain),'current_pain_evidence_url':current_pain[0]['url'] if current_pain else '',
      'carriers_observed':'; '.join(carrier_names),'primary_evidence_url':ops[0]['url'] if ops else '',
      'evidence_excerpt':excerpt(ops[0]['text']) if ops else '',
      'event_types':'; '.join(e['type'] for e in events),'event_evidence_urls':'; '.join(e['url'] for e in events),
      'event_summary':'; '.join(e['summary'] for e in events),'event_dates':'; '.join(e.get('date') or 'unknown' for e in events),
      'source_count':len(all_sources),'source_receipts':'; '.join(sorted(set(s['receipt'] for s in all_sources))),
      'company_profile_url':c.get('url',''),'discovery_task_id':c['discovery_task_id'],
      'shipment_volume':'unknown','annual_parcel_volume_fit':'unverified','budget':'unknown','purchase_intent':'unknown',
      'customer_suppression':'user-supplied known customers excluded; CRM verification unavailable',
      'miss_reason':'; '.join(reason),'as_of':AS_OF.isoformat()}
    return row,all_sources

def csv_write(path, rows):
    if not rows:return
    # Escape spreadsheet formula injection without changing raw JSON records.
    def safe(v):
        if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')):return "'"+v
        return v
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows({k:safe(v) for k,v in r.items()} for r in rows)
    tmp.replace(path)

def build():
    OUT.mkdir(exist_ok=True)
    accounts=read(ROOT/'config/accounts.json');assert len(accounts)==100
    assert len({c['domain'] for c in accounts})==100
    reviews=read(ROOT/'config/event_reviews.json',{})
    evaluated=[evaluate(c,reviews) for c in accounts]
    rows=[r for r,s in evaluated];sources=[dict(company_domain=r['company_domain'],**s) for r,ss in evaluated for s in ss]
    rows.sort(key=lambda r:(-r['score'],-r['recent_event_score'],r['company_domain']))
    contacts=contact_rows()
    for i,r in enumerate(rows,1):
        r['rank']=i
        people=[c for c in contacts if (c.get('companyIdentifier') or c.get('domain'))==r['company_domain']]
        people.sort(key=lambda c: ('logisti' not in c['latest_experience_title'].lower(),'supply' not in c['latest_experience_title'].lower()))
        r['decision_makers_found']=len(people)
        r['decision_maker_names']='; '.join(c['name'] for c in people)
        r['decision_maker_titles']='; '.join(c['latest_experience_title'] for c in people)
        r['decision_maker_linkedin_urls']='; '.join(c['url'] for c in people)
        r['contact_miss_reason']='' if people else 'No accepted current senior logistics, operations, ecommerce or technology buyer found yet'
    # Qualification is a real gate, not an instruction to relabel the first 50 rows.
    top=[r for r in rows if r['qualification_status']=='ICP_qualified'][:50]
    topdomains={r['company_domain'] for r in top}
    selected_contacts=[c for c in contacts if (c.get('companyIdentifier') or c.get('domain')) in topdomains]
    csv_write(OUT/'accounts_100_scored.csv',rows);csv_write(OUT/'top_50_qualified.csv',top)
    personrows=[{'company_domain':c.get('companyIdentifier') or c.get('domain'),'name':c['name'],'title':c['latest_experience_title'],
      'linkedin_url':c['url'],'location':c.get('location_name',''),'role_start_date':c.get('latest_experience_start_date',''),
      'verification_status':c['verification_status'],'source_task_id':c['task_id'],'observed_at':c.get('observed_at','unknown'),
      'role_evidence_urls':'; '.join(c.get('source_urls',[c['url']])),
      'buyer_role':'Implementation sponsor' if re.search(r'\bcio\b|\bcto\b|information|\bit director\b',c['latest_experience_title'],re.I) else 'Business owner / buying committee candidate',
      'budget_authority':'unverified','email':'','email_miss_reason':'Not requested; not guessed or enriched'} for c in selected_contacts]
    csv_write(OUT/'decision_makers.csv',personrows)
    summary={'as_of':AS_OF.isoformat(),'accounts_scored':len(rows),'accounts_researched':sum(bool(r['source_receipts']) for r in rows),
      'icp_qualified_total':sum(r['qualification_status']=='ICP_qualified' for r in rows),'top_qualified_selected':len(top),
      'top_accounts_with_contacts':sum(r['decision_makers_found']>0 for r in top),'decision_makers':len(personrows),
      'accounts_with_reviewed_events':sum(bool(r['event_types']) for r in rows),
      'accounts_with_reviewed_dated_events':sum(any(d and d!='unknown' for d in r['event_dates'].split('; ')) for r in rows),
      'status':'complete' if len(top)==50 and all(r['decision_makers_found'] for r in top) else 'completed_with_contact_gaps' if len(top)==50 else 'incomplete',
      'mode':'live_provider_records_and_live_web_search; local_deterministic_scoring',
      'limitations':['Search-index evidence, not full-page verification for every account','Contacts are provider-current; reconfirm before outreach',
      'No CRM access: customer suppression is limited to supplied list','Account unit is brand/operator domain; shared parent procurement flagged',
      'ICP qualification does not establish budget, shipment volume, buying committee authority or active purchase intent',
      'No unattended schedule deployed; live refresh requires connected agent tools','Clay credit consumption unavailable through connector; no Deepline run executed']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    (OUT/'accounts.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
    (OUT/'source_ledger.json').write_text(json.dumps(sources,indent=2,ensure_ascii=False))
    csv_write(OUT/'contact_gaps.csv',[{'company_name':r['company_name'],'company_domain':r['company_domain'],
        'miss_reason':r['contact_miss_reason'],'routes_tried':'Company-scoped semantic role search; current-title keyword roster; public web role search',
        'evidence_receipts':'; '.join(str(p.relative_to(ROOT)) for p in RAW.glob('*'+r['company_domain']+'*'))} for r in top if not r['decision_makers_found']])
    db=sqlite3.connect(OUT/'shippypro.sqlite3')
    for table,data in [('accounts',rows),('contacts',personrows)]:
        db.execute('CREATE TABLE IF NOT EXISTS '+table+' (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('DELETE FROM '+table)
        for r in data:db.execute('INSERT INTO '+table+' VALUES (?,?)',(r.get('company_domain','')+'|'+r.get('linkedin_url',''),json.dumps(r)))
    db.commit();db.close()
    body=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k in ['rank','company_name','score','event_summary','decision_maker_names'])+'</tr>' for r in top)
    (OUT/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>ShippyPro live account run</title><style>body{font:15px system-ui;margin:40px}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}table{border-collapse:collapse}</style><h1>ShippyPro live account run</h1><pre>'+html.escape(json.dumps(summary,indent=2))+'</pre><table><tr><th>Rank</th><th>Company</th><th>Score</th><th>Reviewed event</th><th>Decision makers</th></tr>'+body+'</table>')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['build']);parser.parse_args();build()
