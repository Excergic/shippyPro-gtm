"""Export source-first account qualification and professional contact enrichment."""
from __future__ import annotations
import csv,html,json,re,runpy,shutil,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/signal_first_v3'
def read(p):return json.loads(p.read_text())
def payload(r):
 if r.get('structuredContent'):return r['structuredContent']
 try:return json.loads(next(c['text'] for c in r.get('content',[]) if c['type']=='text'))
 except (ValueError,StopIteration):return {}
def email_value(c):
 result=[];pending=False
 for e in c.get('enrichments',[]):
  if 'email' not in e.get('name','').lower():continue
  pending|=e.get('state')=='in-progress'
  v=e.get('value')
  try:v=json.loads(v) if isinstance(v,str) else v
  except ValueError:pass
  if isinstance(v,dict):result += [s for s in v.values() if isinstance(s,str) and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',s)]
  elif isinstance(v,str) and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):result.append(v)
 return (result[0] if result else ''),pending

def eligible(c):
 t=c.get('latest_experience_title','')
 if not re.search(r'chief|\bceo\b|\bcoo\b|director|directeur|directrice|head|vice president|\b[es]?vp\b|manager|managing|leiter',t,re.I):return False
 if re.search(r'\bhr\b|human resources|talent|HSE|assistant|supervisor|real estate|retail operations|sales operations|key account manager|brand operations|project cargo|project logistics|digital distribution and programming',t,re.I):return False
 if re.search('marketing',t,re.I) and not re.search('e.?comm',t,re.I):return False
 return bool(re.search(r'supply|logisti|fulfil|e.?comm|operations|operating|digital|distribution|\bcoo\b|\bceo\b|managing director',t,re.I) and c.get('url'))

def collect_contacts(config,domains):
 found={};reject=[]
 files=sorted((OUT/'raw').glob('contacts*.json'))
 for f in files:
  p=payload(read(f))
  for c in p.get('contacts',[]):
   c=dict(c,task_id=p.get('taskId',''),receipt=str(f.relative_to(ROOT)))
   d=config['contact_aliases'].get(c.get('entityId'),c.get('domain',''))
   c['account_domain']=d
   if d not in domains or not eligible(c) or c.get('entityId') in config['rejected_contact_ids']:
    reject.append(dict(c,rejection=config.get('rejected_contact_reasons',{}).get(c.get('entityId'),'Employer, seniority, function or profile gate failed')));continue
   found[c['entityId']]=c
 for f in sorted((OUT/'raw').glob('*context*.json')):
  for c in payload(read(f)).get('contacts',[]):
   if c.get('entityId') not in found:continue
   email,pending=email_value(c);base=found[c['entityId']]
   # Keep a returned value if another search page has a completed null.
   if email:base.update(work_email=email,email_receipt=str(f.relative_to(ROOT)),email_status='provider_returned; deliverability not independently verified')
   elif not base.get('work_email'):base.update(email_status='in_progress' if pending else 'provider_completed_without_email',email_receipt=str(f.relative_to(ROOT)))
 for c in found.values():
  c.setdefault('work_email','');c.setdefault('email_status','not_requested');c.setdefault('email_receipt','')
  v=config.get('verified_names',{}).get(c['entityId'],{});c['display_name']=v.get('name',c['name']);c['identity_source']=v.get('source',c['url'])
  c['current_role_status']='provider_reported_current; independently reconfirm before outreach'
  ed=c['work_email'].rsplit('@',1)[-1].lower() if c['work_email'] else ''
  c['email_domain_status']='same_account_domain' if ed and (ed==c['account_domain'] or ed.endswith('.'+c['account_domain'])) else 'alternate_domain_affiliation_needs_verification' if ed else 'no_email'
  if c.get('work_email') and c['email_domain_status'].startswith('alternate'):c['email_status']+='; alternate email domain requires affiliation check'
  if c['entityId']=='243642776':c['latest_experience_title']='Executive Vice President and Chief Digital Officer';c['identity_source']='https://ir.kroger.com/governance/executive-management/default.aspx'
 # Publicly attributed logistics owner. Two named provider searches missed him.
 if 'asda.com' in domains:
  found['public-chris-hall']={'entityId':'public-chris-hall','name':'Chris Hall','display_name':'Chris Hall','account_domain':'asda.com','latest_experience_title':'Vice President of Logistics','url':'https://uk.linkedin.com/in/chris-hall-7285b54','identity_source':'https://www.retail-week.com/fashion/george-at-asda-and-dhl-team-up-on-next-generation-fulfilment-centre/7050755.article','receipt':'results/signal_first_v3/raw/contact-web-extra-3.json','task_id':'','work_email':'','email_status':'provider_identity_not_resolved_after_domain_and_linkedin_routes','email_receipt':'results/signal_first_v3/raw/contacts-named-alt.json','current_role_status':'March 2026 project attribution plus public employer profile; reconfirm before outreach'}
 return list(found.values()),reject

def write_csv(path,rows,fields):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def build():
 config=read(ROOT/'config/signal_first.json')
 # The assessment reads only the source-discovered v3 manifest, never the old roster.
 runpy.run_path(str(ROOT/'src/signal_assessment.py'))['build_assessment'](config)
 rs=read(OUT/'scored_accounts.json');selected=[r for r in rs if r['qualification']=='qualified'][:config['selected_accounts']]
 domains={r['domain'] for r in selected};contacts,rejected=collect_contacts(config,domains)
 primary=[]
 for r in selected:
  d=r['domain'];pr=r['profile'];cs=[c for c in contacts if c['account_domain']==d];preferred=config['preferred_contacts'].get(d,'')
  cs.sort(key=lambda c:(bool(c.get('work_email')),c['name']==preferred,bool(re.search('chief|coo|supply|logisti|fulfil',c.get('latest_experience_title',''),re.I))),reverse=True)
  c=cs[0] if cs else {}
  r['primary_contact']=c
  r.update(country=pr.get('country',''),company_linkedin=pr.get('url',''),employee_count=pr.get('employee_count',''),revenue_range=pr.get('annual_revenue',''),company_profile=f"{r['sector']}; {pr.get('country','HQ not established')}; {pr.get('employee_count','unknown')} provider-reported employees. {r['signal']}",decision_maker=c.get('display_name',''),job_title=c.get('latest_experience_title',''),linkedin=c.get('url',''),work_email=c.get('work_email',''),email_status=c.get('email_status','contact_not_resolved'),email_receipt=c.get('email_receipt',''),contact_source=c.get('identity_source',''),contact_receipt=c.get('receipt',''),role_status=c.get('current_role_status','not resolved'),email_domain_status=c.get('email_domain_status','no_email'),phone='',phone_status='not sourced',miss_reason='' if c.get('work_email') else c.get('email_status','Contact not resolved'),website='https://'+d,observed_at=config['as_of'])
  if c:primary.append(c['entityId'])
 fields=['rank','company','domain','website','country','sector','company_profile','company_linkedin','employee_count','revenue_range','annual_shipments','scale_basis','signal','event_date','date_basis','signal_class','confirmed_purchase_intent','signal_caveat','source_url','source_title','receipt','signal_age_days','signal_status','icp_score','fit_geography','fit_parcels','fit_vertical','fit_scale','fit_complexity','priority_score','qualification','exclusion_reason','decision_maker','job_title','linkedin','work_email','email_status','email_domain_status','phone','phone_status','contact_source','contact_receipt','email_receipt','role_status','miss_reason','observed_at','scoring_state','model_version']
 write_csv(OUT/'top_50_enriched.csv',selected,fields)
 write_csv(OUT/'accounts_100_scored.csv',rs,[x for x in fields if x not in ['decision_maker','job_title','linkedin','work_email','email_status','email_domain_status','phone','phone_status','contact_source','contact_receipt','email_receipt','role_status','miss_reason','observed_at','scoring_state','model_version']])
 # Exactly one primary person per selected company; gaps remain visible.
 crows=[dict(company=r['company'],domain=r['domain'],decision_maker=r['decision_maker'],job_title=r['job_title'],linkedin=r['linkedin'],work_email=r['work_email'],email_status=r['email_status'],contact_source=r['contact_source'],contact_receipt=r['contact_receipt'],email_receipt=r['email_receipt'],role_status=r['role_status'],miss_reason=r['miss_reason']) for r in selected]
 write_csv(OUT/'decision_makers_50.csv',crows,list(crows[0]))
 write_csv(OUT/'additional_contacts.csv',[dict(company_domain=c['account_domain'],name=c['display_name'],title=c['latest_experience_title'],linkedin=c['url'],work_email=c.get('work_email',''),email_status=c['email_status'],source_receipt=c['receipt'],email_receipt=c['email_receipt']) for c in contacts if c['entityId'] not in primary],['company_domain','name','title','linkedin','work_email','email_status','source_receipt','email_receipt'])
 summary={'as_of':config['as_of'],'candidate_accounts':len(rs),'qualified_accounts':sum(r['qualification']=='qualified' for r in rs),'selected_accounts':len(selected),'primary_contacts':sum(bool(r['decision_maker']) for r in selected),'primary_work_emails':sum(bool(r['work_email']) for r in selected),'all_relevant_contacts':len(contacts),'all_work_emails':sum(bool(c['work_email']) for c in contacts),'confirmed_purchase_intent':sum(r['confirmed_purchase_intent'] for r in selected),'scoring_state':'exploratory_end_to_end; no predictive validation','pricing':'Unknown: connected tools do not expose credit receipts','execution':'Live connected web and Clay calls; Python rebuilds preserved receipts','schedule_deployed':False,'outreach_sent':0}
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2));(OUT/'selected_accounts.json').write_text(json.dumps(selected,indent=2));(OUT/'rejected_contacts.json').write_text(json.dumps(rejected,indent=2))
 render(selected,summary)
 for name in ['top_50_enriched.csv','accounts_100_scored.csv','decision_makers_50.csv','additional_contacts.csv','summary.json','report.html']:
  shutil.copyfile(OUT/name,ROOT/'results'/name)

 shutil.copyfile(OUT/'top_50_enriched.csv',ROOT/'results/top_50_qualified.csv')
 shutil.copyfile(OUT/'decision_makers_50.csv',ROOT/'results/decision_makers.csv')
 gaps=[r for r in crows if not r['work_email']]
 write_csv(OUT/'contact_gaps.csv',gaps,list(crows[0]));shutil.copyfile(OUT/'contact_gaps.csv',ROOT/'results/contact_gaps.csv')
 (ROOT/'results/accounts.json').write_text(json.dumps(rs,indent=2))
 (ROOT/'results/source_ledger.json').write_text((OUT/'source_catalog.json').read_text())
 (ROOT/'results/excluded.json').write_text(json.dumps([r for r in rs if r['qualification']=='excluded'],indent=2))
 receipt=dict(summary,discovery_queries=32,unique_discovery_source_urls=len(read(OUT/'source_catalog.json')),raw_receipts=len(list((OUT/'raw').glob('*.json'))),provider_routes=['connected public web search','Clay company profile search','Clay role-based and named person search','Clay work-email enrichment','public professional-profile recovery'],cost_receipt_available=False)
 (OUT/'live_run.json').write_text(json.dumps(receipt,indent=2));(ROOT/'results/live_run.json').write_text(json.dumps(receipt,indent=2))
 db=ROOT/'results/shippypro.sqlite3'
 with sqlite3.connect(db) as conn:
  for table in ['accounts','contacts','sources']:conn.execute('DROP TABLE IF EXISTS '+table)
  conn.execute('CREATE TABLE accounts(domain TEXT PRIMARY KEY,company TEXT,icp_score REAL,qualification TEXT,selected INTEGER,signal TEXT,event_date TEXT,source_url TEXT,details_json TEXT)')
  for r in rs:conn.execute('INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?)',(r['domain'],r['company'],r['icp_score'],r['qualification'],int(r['domain'] in domains),r['signal'],r['event_date'],r['source_url'],json.dumps(r)))
  conn.execute('CREATE TABLE contacts(entity_id TEXT PRIMARY KEY,account_domain TEXT,name TEXT,title TEXT,linkedin TEXT,work_email TEXT,email_status TEXT,is_primary INTEGER,details_json TEXT)')
  for c in contacts:conn.execute('INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?,?)',(c['entityId'],c['account_domain'],c['display_name'],c['latest_experience_title'],c['url'],c.get('work_email',''),c['email_status'],int(c['entityId'] in primary),json.dumps(c)))
  conn.execute('CREATE TABLE sources(source_id TEXT PRIMARY KEY,url TEXT,title TEXT,receipt TEXT)')
  for src in read(OUT/'source_catalog.json'):conn.execute('INSERT INTO sources VALUES (?,?,?,?)',(src['id'],src['url'],src['title'],src['receipt']))
 print(json.dumps(summary,indent=2));return summary

def render(rs,summary):
 esc=lambda v:html.escape(str(v or ''))
 rows=[]
 for r in rs:
  link=lambda u,t:f'<a href="{esc(u)}" target="_blank" rel="noreferrer">{esc(t)}</a>' if u else esc(t)
  rows.append('<tr>'+''.join(f'<td>{v}</td>' for v in [r['rank'],link(r['website'],r['company'])+'<small>'+esc(r['company_profile'])+'</small>',f"<b>{r['icp_score']}/100</b><small>Priority {r['priority_score']}</small>",esc(r['signal'])+'<small>'+esc(r['event_date'])+' · '+link(r['source_url'],'Evidence')+'</small>',link(r['linkedin'],r['decision_maker'])+'<small>'+esc(r['job_title'])+'</small>',esc(r['work_email'] or 'Email not resolved')+'<small>'+esc(r['email_status'])+'</small>'])+'</tr>')
 body='''<!doctype html><html lang="en"><meta charset="utf-8"><title>ShippyPro signal-first shortlist</title><style>body{font:15px system-ui;background:#f6f7fb;color:#172033;margin:32px}h1{font-size:28px}p{max-width:1000px}a{color:#2159ba}nav{display:flex;gap:22px;margin:20px 0}input{padding:12px;width:420px;max-width:90%;border:1px solid #bdc6d5;border-radius:6px}table{border-collapse:collapse;width:100%;background:white;margin-top:18px}th,td{text-align:left;padding:14px;border-bottom:1px solid #e4e8f0;vertical-align:top}th{background:#172033;color:white;position:sticky;top:0}small{display:block;color:#637083;line-height:1.5;margin-top:7px}td:nth-child(2){max-width:270px}td:nth-child(4){max-width:340px}</style>'''
 body+=f"<h1>ShippyPro · Signal-first account shortlist</h1><p>As of {summary['as_of']}. {summary['candidate_accounts']} accounts scored → {summary['selected_accounts']} selected → {summary['primary_contacts']} primary contacts → {summary['primary_work_emails']} work emails returned.</p>"
 body+='<p>These are public buying signals: business changes that suggest a shipping need. No active shipping-software evaluation has been established. ICP scores are transparent heuristics, not purchase probabilities. Shipment volumes remain unverified. Emails are provider-returned and have no independent deliverability check.</p><nav><a href="top_50_enriched.csv">Download full shortlist</a><a href="decision_makers_50.csv">Download 50 contacts</a><a href="accounts_100_scored.csv">Review all 100</a><a href="additional_contacts.csv">Additional contacts</a></nav><input id="q" aria-label="Search shortlist" placeholder="Search company, signal, role or email"><table><thead><tr><th>#</th><th>Company profile</th><th>ICP fit</th><th>Buying signal</th><th>Decision-maker</th><th>Work email</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><script>document.querySelector("#q").addEventListener("input",e=>{const q=e.target.value.toLowerCase();for(const r of document.querySelectorAll("tbody tr"))r.hidden=!r.textContent.toLowerCase().includes(q)});</script></html>'
 (OUT/'report.html').write_text(body)
if __name__=='__main__':build()
