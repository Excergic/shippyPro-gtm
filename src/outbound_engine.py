"""Evidence-linked campaign drafts and durable ghost-audit tracking. No send transport."""
from __future__ import annotations
import argparse,csv,hashlib,html,json,re,sqlite3,sys,unicodedata,uuid,tempfile
from datetime import datetime,timezone
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/outbound_v1';DB=OUT/'campaign.sqlite3';CFG=ROOT/'config/outbound/campaign.json'
sys.path.insert(0,str(ROOT/'src'))
from icp_pipeline import parse_sources

def now():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())
def stable(s):return hashlib.sha256(s.encode()).hexdigest()[:20]
def norm(s):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def profile_key(s):
 u=urlsplit(s);return u.path.rstrip('/').lower() if ((u.hostname or '')=='linkedin.com' or (u.hostname or '').endswith('.linkedin.com')) and u.path.startswith('/in/') else ''
def connect(db=DB):
 db=Path(db);db.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(db);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c

def init(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY,domain TEXT UNIQUE NOT NULL,rank INTEGER NOT NULL,name TEXT NOT NULL,company TEXT NOT NULL,email TEXT,linkedin TEXT NOT NULL,title TEXT,research_json TEXT NOT NULL,review_status TEXT NOT NULL DEFAULT 'unreviewed',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,contact_id TEXT NOT NULL REFERENCES contacts(id),step INTEGER NOT NULL,day_offset INTEGER NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,evidence_json TEXT NOT NULL,content_hash TEXT NOT NULL,review_status TEXT NOT NULL DEFAULT 'draft',edited INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(contact_id,step));
 CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,operation_hash TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,contact_id TEXT NOT NULL REFERENCES contacts(id),message_id TEXT REFERENCES messages(id),type TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
 ''');c.commit()

def web_sources(file):
 if not file.exists():return []
 r=read(file);p=r.get('result',r);txt='\n'.join(x.get('text','') for x in p.get('content',[]) if x.get('type')=='text')
 return [dict(x,receipt=str(file.relative_to(ROOT))) for x in parse_sources(txt)]

def angles():
 fields=['domain','greeting','subject','opener','question','diagnostic','feature','metric','persona','personal_fact'];result={}
 for line in (ROOT/'config/outbound/angles.tsv').read_text().splitlines():
  parts=line.split('|')
  if len(parts)!=10:raise ValueError('Malformed angle row: '+line[:80])
  a=dict(zip(fields,parts));result[a['domain']]=a
 return result

FEATURES={
 'routing':{'claim':'ShippyPro supports rule-based carrier selection and label generation.','url':'https://www.shippypro.com/en/shipping-platform','scenario':'carrier rules, labels and the resulting delivery events'},
 'api':{'claim':'ShippyPro provides shipping APIs and configurable carrier rules.','url':'https://www.shippypro.com/en/shipping-platform','scenario':'the system handoff into labels, carrier rules and delivery events'},
 'tracking':{'claim':'ShippyPro brings shipment tracking into the order-to-delivery workflow.','url':'https://www.shippypro.com/en/onestock-shippypro-integration','scenario':'shipment visibility and the next action on a delivery exception'},
 'invoice':{'claim':'ShippyPro can compare shipping data with carrier invoices to surface discrepancies.','url':'https://help.shippypro.com/en/knowledge/how-the-new-invoice-analysis-tool-works-beta','scenario':'expected shipping costs, invoice line items and the discrepancies between them'}
}
REVIEW_FLAGS={
 'nfiindustries.com':['Current professional role not independently corroborated by the fresh public search; confirm the contact before use.'],
 'arvato.com':['Public profile is Turkey/automotive oriented; ownership of the Spanish beauty/fashion project is not established.'],
 'shein.com':['Public remit is Latin America and Caribbean; not the owner established for the Indiana facility signal.'],
 'bergzeit.de':['Provider says Head; public profile describes logistics teamlead/planning. Reconcile seniority and buying authority.'],
 'groupe-blondel.com':['Public profile emphasises site responsibility; business-unit scope differs from provider title.'],
 'levistrauss.com':['Exact VP title and US/Canada/Europe project ownership not independently corroborated.'],
 'kavehome.com':['Confirm a meaningful parcel-eligible flow; no promise of bulky-furniture or freight planning.'],
 'bauhaus.info':['Separate parcel-eligible ecommerce from bulky DIY deliveries.'],
 'haier-europe.com':['Confirm parcel-eligible flow and UK project ownership; no appliance-delivery capability is assumed.'],
 'vente-unique.com':['Confirm parcel scope before proposing parcel software for a furniture-led operation.'],
 'thekrogerco.com':['Verify parcel scope and owner; grocery last-mile orchestration is outside the assumed product scenario.'],
 'phlur.com':['Verify fragrance dangerous-goods restrictions and actual carrier eligibility.'],
 'benettongroup.com':['Production/supply-chain affiliation does not itself prove parcel-software ownership.']
}

def research(r,a):
 rank=r['rank'];f=OUT/'raw'/('pilot-'+str(rank-1)+'.json' if rank<=3 else f'person-{rank:02d}.json');sources=web_sources(f)
 if r['domain']=='savers.co.uk':sources+=web_sources(OUT/'raw/recovery-1.json')
 if r['domain']=='pureseoul.co.uk':sources+=web_sources(ROOT/'results/signal_first_v3/raw/contact-web-1.json')
 key=profile_key(r['linkedin']);person_tokens=[norm(t) for t in re.findall(r'\w+',r['decision_maker']) if len(t)>2 and norm(t) not in {'pmp','rad'}]
 relevant=[]
 for s in sources:
  exact=bool(key and profile_key(s['url'])==key)
  title=norm(s['title']);named=sum(t in title for t in person_tokens)>=min(2,len(person_tokens)) and bool(person_tokens)
  # Ignore generic result matches such as NFL "NFI" and unrelated profiles.
  body=norm(s['text']);business_named=norm(r['decision_maker'].replace(', PMP','')) in body and bool(person_tokens) and norm(r['company']).replace('group','') in norm(s['title']+' '+s['text'])
  if exact or named or business_named:relevant.append(dict(url=s['url'],title=s['title'],receipt=s['receipt'],identity_match='exact_profile' if exact else 'named_business_source',date_status='publication date not independently normalised'))
 flags=list(REVIEW_FLAGS.get(r['domain'],[]))
 if not r['work_email']:flags.append('Current work email unresolved; preserve the profile and do not guess an address.')
 if r.get('email_domain_status','').startswith('alternate'):flags.append('Provider email uses an alternate domain; affiliation needs checking.')
 return {'research_status':'public_business_context_found' if relevant else 'provider_context_only_after_public_search','researched_at':read(CFG)['research_as_of'],'observed_company_event':r['signal'],'event_date':r['event_date'],'company_source':r['source_url'],'company_receipt':r['receipt'],'person_public_fact':a['personal_fact'],'person_fact_status':'source-grounded business summary' if relevant else 'provider-reported; public corroboration unresolved','person_sources':relevant[:4],'search_receipt':str(f.relative_to(ROOT)),'reported_role':r['job_title'],'persona_hypothesis':a['persona'],'need_hypothesis':a['question'],'hypothesis_status':'untested; no internal pain, budget or vendor evaluation established','suggested_diagnostic':a['diagnostic'],'proposed_measure':a['metric'],'product_capability_source':FEATURES[a['feature']]['url'],'review_flags':flags,'signal_caveat':r['signal_caveat'],'email_status':r['email_status'],'email_domain_status':r.get('email_domain_status','no_email')}

def drafts(r,a,cfg):
 name=a['greeting'];feature=FEATURES[a['feature']];diagnostic=a['diagnostic'][0].upper()+a['diagnostic'][1:]
 bodies=[
 f"Hi {name},\n\n{a['opener']}\n\n{a['question']}\n\n{feature['claim']} A useful starting point could be to {a['diagnostic']}.\n\nWould that be a relevant scenario to explore in a ShippyPro demo?",
 f"Hi {name},\n\nOne practical way to make the question concrete: {a['diagnostic']}.\n\nThe useful measure would be {a['metric']}. That gives your team a specific check before considering any change.\n\nIs that already covered in {r['company']}'s current setup?",
 f"Hi {name},\n\nFor {r['company']}, a focused ShippyPro demo could examine {feature['scenario']}, using the scenario above as the starting point.\n\nThe useful check is whether the workflow fits the systems and carriers already in place. {a['question']}\n\nIf useful, ShippyPro's public demo request form is here:\n{cfg['official_demo_url']}",
 f"Hi {name},\n\nClosing the loop on {r['company']}'s shipping workflow. The question I would leave with your team is: {a['question'][0].lower()+a['question'][1:]}\n\nIf the current setup already handles that well, there may be nothing to change. If it is worth examining, the ShippyPro demo form in the previous note is the next step.\n\nOtherwise, happy to leave it here."
 ]
 subjects=[a['subject'],'A practical check for '+r['company'],'A focused shipping scenario','Closing the loop']
 evid=[r['source_url'],feature['url'],r['linkedin']]
 return [dict(step=i+1,day_offset=cfg['sequence_business_day_offsets'][i],subject=subjects[i],body=b,evidence=evid,core_value_proposition=feature['scenario'],message_kind='proposed_shippypro_campaign_copy',cta_type=['demo_interest','diagnostic_question','public_demo_form','close_loop'][i]) for i,b in enumerate(bodies)]

def qa_message(m):
 issues=[];words=len(m['body'].split())
 if words>140:issues.append('over_140_words')
 if len(m['subject'].split())>9:issues.append('subject_over_9_words')
 for pat in [r'guarantee',r'we (?:already|have) (?:audited|analysed|analyzed)',r'our mutual',r'noticed you(?:.re| are) struggling',r'\d+% (?:saving|reduction)',r'\{\{',r'\[sender']:
  if re.search(pat,m['body'],re.I):issues.append('unsupported_or_placeholder_copy:'+pat)
 return issues

def event(c,cid,kind,payload,mid=None,eid=None):
 eid=eid or uuid.uuid4().hex
 existing=c.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
 if existing:
  if existing['contact_id']!=cid or existing['type']!=kind or json.loads(existing['payload_json'])!=payload or existing['message_id']!=mid:raise ValueError('Event ID already belongs to a different operation')
  return eid
 c.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(eid,cid,mid,kind,json.dumps(payload),now()));return eid

def build(db=DB):
 cfg=read(CFG)
 if cfg['mode']!='ghost_audit' or cfg['sending_enabled'] or cfg['transport']!='none':raise ValueError('This engine is scoped to an independent ghost audit; no sending transport exists')
 rs=read(ROOT/cfg['primary_source']);aa=angles();OUT.mkdir(exist_ok=True,parents=True)
 if len(rs)!=50 or len({r['domain'] for r in rs})!=50:raise ValueError('Expected the 50 distinct selected accounts')
 c=connect(db);init(c);quality=[]
 with c:
  for r in rs:
   cid=stable(cfg['campaign_id']+'|'+r['domain']+'|'+profile_key(r['linkedin']));a=aa[r['domain']];rr=research(r,a);t=now()
   old=c.execute('SELECT * FROM contacts WHERE id=?',(cid,)).fetchone()
   other=c.execute('SELECT id FROM contacts WHERE domain=?',(r['domain'],)).fetchone()
   if other and other['id']!=cid:raise ValueError('Contact identity changed for '+r['domain']+'; create a new campaign version rather than reassigning old messages')
   c.execute('INSERT INTO contacts(id,domain,rank,name,company,email,linkedin,title,research_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET rank=excluded.rank,name=excluded.name,company=excluded.company,email=excluded.email,linkedin=excluded.linkedin,title=excluded.title,research_json=excluded.research_json,updated_at=excluded.updated_at',(cid,r['domain'],r['rank'],r['decision_maker'],r['company'],r['work_email'],r['linkedin'],r['job_title'],json.dumps(rr),t,t))
   if not old:event(c,cid,'research_recorded',{'mode':'ghost_audit','source':rr['search_receipt'],'research_status':rr['research_status']},eid='research-'+cid)
   changed=False
   for m in drafts(r,a,cfg):
    mid=cid+'-'+str(m['step']);h=stable(m['subject']+'\n'+m['body']);prior=c.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone()
    issues=qa_message(m);quality.append(dict(contact_id=cid,company=r['company'],step=m['step'],word_count=len(m['body'].split()),issues=issues))
    if not prior:
     c.execute('INSERT INTO messages(id,contact_id,step,day_offset,subject,body,evidence_json,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,cid,m['step'],m['day_offset'],m['subject'],m['body'],json.dumps(m['evidence']),h,t,t));event(c,cid,'draft_created',{'step':m['step'],'content_hash':h},mid,eid='draft-'+mid)
    elif not prior['edited'] and prior['content_hash']!=h:
     c.execute("UPDATE messages SET subject=?,body=?,evidence_json=?,content_hash=?,review_status='draft',revision=revision+1,updated_at=? WHERE id=?",(m['subject'],m['body'],json.dumps(m['evidence']),h,t,mid));event(c,cid,'draft_regenerated',{'old_hash':prior['content_hash'],'new_hash':h},mid);changed=True
   if changed or (old and old['research_json']!=json.dumps(rr)):
    c.execute("UPDATE contacts SET review_status='unreviewed' WHERE id=?",(cid,));c.execute("UPDATE messages SET review_status='draft' WHERE contact_id=?",(cid,))
  (OUT/'copy_qa.json').write_text(json.dumps(quality,indent=2))
  if any(x['issues'] for x in quality):raise ValueError('Copy QA failed; inspect copy_qa.json')
 c.close();data=export(db);print(json.dumps(data['summary'],indent=2));return data

def state(db=DB):
 c=connect(db);init(c);contacts=[]
 for row in c.execute('SELECT * FROM contacts ORDER BY rank'):
  r=dict(row);r['research']=json.loads(r.pop('research_json'));r['messages']=[]
  for m in c.execute('SELECT * FROM messages WHERE contact_id=? ORDER BY step',(r['id'],)):
   mm=dict(m);mm['evidence']=json.loads(mm.pop('evidence_json'));r['messages'].append(mm)
  r['timeline']=[dict(id=e['id'],type=e['type'],created_at=e['created_at'],payload=json.loads(e['payload_json'])) for e in c.execute('SELECT * FROM events WHERE contact_id=? ORDER BY created_at,id',(r['id'],))]
  r['engagement_status']='not_contacted';contacts.append(r)
 counts=dict(c.execute('SELECT type,count(*) FROM events GROUP BY type').fetchall());c.close()
 summary={'contacts':len(contacts),'research_attempted':len(contacts),'public_business_context_found':sum(x['research']['research_status']=='public_business_context_found' for x in contacts),'draft_messages':sum(len(x['messages']) for x in contacts),'reviewed_contacts':sum(x['review_status']=='reviewed' for x in contacts),'work_emails':sum(bool(x['email']) for x in contacts),'missing_emails':sum(not x['email'] for x in contacts),'contacts_with_review_flags':sum(bool(x['research']['review_flags']) for x in contacts),'sent':0,'replies':0,'demos_booked':0,'mode':'ghost_audit','sending_enabled':False,'scheduled_messages':0,'transport':'none'}
 return dict(campaign=read(CFG),summary=summary,contacts=contacts,event_counts=counts)

def writecsv(path,rows,fields):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def export(db=DB):
 data=state(db);flat=[];long=[]
 for r in data['contacts']:
  rr=r['research'];row={k:r[k] for k in ['id','rank','company','domain','name','title','email','linkedin','review_status','note']}
  row.update(mode='ghost_audit',research_status=rr['research_status'],company_event=rr['observed_company_event'],event_date=rr['event_date'],company_evidence_url=rr['company_source'],person_fact=rr['person_public_fact'],person_sources=' | '.join(s['url'] for s in rr['person_sources']),need_hypothesis=rr['need_hypothesis'],proposed_diagnostic=rr['suggested_diagnostic'],proposed_measure=rr['proposed_measure'],review_flags=' | '.join(rr['review_flags']),email_status=rr['email_status'],engagement_status='not_contacted',sending_enabled=False)
  for m in r['messages']:
   for key in ['subject','body','day_offset','review_status']:row[f'step_{m["step"]}_{key}']=m[key]
   long.append(dict(contact_id=r['id'],company=r['company'],contact_name=r['name'],work_email=r['email'],message_id=m['id'],step=m['step'],proposed_business_day_offset=m['day_offset'],subject=m['subject'],body=m['body'],review_status=m['review_status'],revision=m['revision'],source_urls=' | '.join(m['evidence']),sent_at='',provider_message_id='',mode='ghost_audit'))
  flat.append(row)
 writecsv(OUT/'campaign_contacts_50.csv',flat,list(flat[0]));writecsv(OUT/'campaign_messages_200.csv',long,list(long[0]))
 (OUT/'campaign.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));(OUT/'summary.json').write_text(json.dumps(data['summary'],indent=2))
 research_rows=[dict(contact_id=x['id'],company=x['company'],person=x['name'],**x['research']) for x in data['contacts']];(OUT/'research_50.json').write_text(json.dumps(research_rows,ensure_ascii=False,indent=2))
 render(data)
 if Path(db).resolve()==DB.resolve():
  from shippypro_db import sync
  sync(data)
 return data

def update(db,op,export_outputs=True):
 if op.get('action') not in {'review','edit_message','note'}:raise ValueError('Only audit review, draft edits and notes are supported; no send or engagement simulation')
 c=connect(db);init(c);cid=op.get('contact_id','')
 if not c.execute('SELECT 1 FROM contacts WHERE id=?',(cid,)).fetchone():raise ValueError('Unknown contact')
 request_id=op.get('event_id');request_hash=stable(json.dumps({k:v for k,v in op.items() if k!='event_id'},sort_keys=True))
 if request_id:
  previous=c.execute('SELECT operation_hash FROM requests WHERE id=?',(request_id,)).fetchone()
  if previous:
   c.close()
   if previous['operation_hash']!=request_hash:raise ValueError('Request ID belongs to a different operation')
   return state(db)
 with c:
  if op['action']=='review':
   status=op.get('status')
   if status not in {'reviewed','needs_revision','unreviewed'}:raise ValueError('Invalid review status')
   c.execute('UPDATE contacts SET review_status=?,updated_at=? WHERE id=?',(status,now(),cid));c.execute('UPDATE messages SET review_status=?,updated_at=? WHERE contact_id=?',('reviewed' if status=='reviewed' else 'draft',now(),cid));event(c,cid,'audit_review_changed',{'status':status},eid=op.get('event_id'))
  elif op['action']=='note':
   note=op.get('note','')
   if not isinstance(note,str) or len(note)>6000:raise ValueError('Invalid note')
   c.execute('UPDATE contacts SET note=?,updated_at=? WHERE id=?',(note,now(),cid));event(c,cid,'audit_note_updated',{'note':note},eid=op.get('event_id'))
  else:
   m=c.execute('SELECT * FROM messages WHERE id=? AND contact_id=?',(op.get('message_id'),cid)).fetchone()
   if not m:raise ValueError('Unknown message for contact')
   if op.get('revision')!=m['revision']:raise ValueError('Draft changed since it was opened; refresh before saving')
   sub=op.get('subject','').strip();body=op.get('body','').strip()
   if not sub or not body or len(sub)>180 or len(body)>6000:raise ValueError('Invalid draft length')
   if '\n' in sub or '\r' in sub:raise ValueError('Subject cannot contain newlines')
   h=stable(sub+'\n'+body);c.execute("UPDATE messages SET subject=?,body=?,content_hash=?,review_status='draft',edited=1,revision=revision+1,updated_at=? WHERE id=?",(sub,body,h,now(),m['id']));c.execute("UPDATE contacts SET review_status='unreviewed',updated_at=? WHERE id=?",(now(),cid));event(c,cid,'draft_edited',{'old_hash':m['content_hash'],'new_hash':h,'revision':m['revision']+1},m['id'],op.get('event_id'))
   if request_id:c.execute('INSERT INTO requests VALUES(?,?,?)',(request_id,request_hash,now()))
 c.close();return export(db) if export_outputs else state(db)

def render(data):
 template=(ROOT/'src/outbound_dashboard.html').read_text();safe=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
 (OUT/'campaign.html').write_text(template.replace('__CAMPAIGN_DATA__',safe))


def apply_backup(path,db=DB):
 backup=read(Path(path));cfg=read(CFG)
 if backup.get('campaign_id')!=cfg['campaign_id']:raise ValueError('Backup belongs to another campaign')
 saved=backup.get('contacts',{})
 if not isinstance(saved,dict) or len(saved)>50:raise ValueError('Invalid backup contact population')
 bh=stable(json.dumps(backup,sort_keys=True));key='backup-'+bh
 current=connect(db);init(current)
 if current.execute('SELECT 1 FROM requests WHERE id=?',(key,)).fetchone():current.close();return state(db)
 # Validate and apply on a transactional copy. A conflict never partially writes
 # the user's current tracker or overwrites a separately edited draft.
 with tempfile.TemporaryDirectory() as td:
  staged=Path(td)/'campaign.sqlite3';dest=connect(staged);current.backup(dest);dest.close();current.close()
  for cid,changes in saved.items():
   c=connect(staged)
   if not c.execute('SELECT 1 FROM contacts WHERE id=?',(cid,)).fetchone():c.close();raise ValueError('Backup contains an unknown contact')
   messages=changes.get('messages',{})
   if not isinstance(messages,dict) or len(messages)>4:c.close();raise ValueError('Invalid backup messages')
   for mid,m in messages.items():
    before=c.execute('SELECT * FROM messages WHERE id=? AND contact_id=?',(mid,cid)).fetchone()
    if not before or before['content_hash']!=m.get('base_hash'):c.close();raise ValueError('Draft conflict: review against the current campaign before importing')
    update(staged,dict(action='edit_message',contact_id=cid,message_id=mid,revision=before['revision'],subject=m.get('subject',''),body=m.get('body',''),event_id=key+'-'+mid),export_outputs=False)
   c.close()
   if 'note' in changes:update(staged,dict(action='note',contact_id=cid,note=changes['note'],event_id=key+'-note-'+cid),export_outputs=False)
   if 'review_status' in changes:update(staged,dict(action='review',contact_id=cid,status=changes['review_status'],event_id=key+'-review-'+cid),export_outputs=False)
  c=connect(staged)
  with c:c.execute('INSERT INTO requests VALUES(?,?,?)',(key,bh,now()))
  dest=connect(db);c.backup(dest);dest.close();c.close()
 return export(db)

def resolve_contact(value,db=DB):
 c=connect(db);rows=c.execute('SELECT id FROM contacts WHERE id=? OR domain=? OR name=?',(value,value,value)).fetchall();c.close()
 if len(rows)!=1:raise ValueError('Supply one exact contact ID, domain or name')
 return rows[0]['id']

def serve(port,db=DB):
 class Handler(BaseHTTPRequestHandler):
  def send(self,code,body,kind='application/json'):
   raw=body.encode();self.send_response(code);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
  def do_GET(self):
   if self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:return self.send(403,'{"error":"Invalid host"}')
   if self.path=='/api/campaign':return self.send(200,json.dumps(state(db),ensure_ascii=False))
   name=self.path.split('?',1)[0].lstrip('/') or 'campaign.html'
   if name not in {'campaign.html','campaign_contacts_50.csv','campaign_messages_200.csv','research_50.json','summary.json'}:return self.send(404,'{"error":"Not found"}')
   path=OUT/name
   if not path.exists():return self.send(404,'{"error":"Build the campaign first"}')
   self.send(200,path.read_text(),'text/html' if name.endswith('.html') else 'text/csv' if name.endswith('.csv') else 'application/json')
  def do_POST(self):
   origin=self.headers.get('Origin');host=self.headers.get('Host')
   if host not in {f'127.0.0.1:{port}',f'localhost:{port}'}:return self.send(403,'{"error":"Invalid host"}')
   if origin and origin not in {'http://'+host}:return self.send(403,'{"error":"Cross-origin writes are not allowed"}')
   if self.path!='/api/update' or self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(400,'{"error":"Expected an audit update as JSON"}')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if n<1 or n>32000:raise ValueError('Invalid request size')
    op=json.loads(self.rfile.read(n));data=update(db,op);self.send(200,json.dumps(data,ensure_ascii=False))
   except (ValueError,AssertionError,KeyError,json.JSONDecodeError) as e:self.send(400,json.dumps({'error':str(e)}))
  def log_message(self,*args):pass
 print(f'Ghost-audit tracker: http://127.0.0.1:{port} (no sending transport)',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

def main():
 p=argparse.ArgumentParser(description='ShippyPro independent audit: research, drafts and review; no sending')
 p.add_argument('command',choices=['build','summary','review','note','edit','import-review','serve'])
 p.add_argument('--db',default=str(DB));p.add_argument('--contact');p.add_argument('--status');p.add_argument('--text')
 p.add_argument('--message');p.add_argument('--subject');p.add_argument('--body');p.add_argument('--revision',type=int)
 p.add_argument('--file');p.add_argument('--port',type=int,default=8765)
 args=p.parse_args()
 try:
  if args.command=='build':build(args.db)
  elif args.command=='summary':print(json.dumps(state(args.db)['summary'],indent=2))
  elif args.command=='serve':serve(args.port,args.db)
  elif args.command=='import-review':
   if not args.file:p.error('import-review requires --file')
   print(json.dumps(apply_backup(args.file,args.db)['summary'],indent=2))
  else:
   if not args.contact:p.error(args.command+' requires --contact')
   op={'action':{'review':'review','note':'note','edit':'edit_message'}[args.command],'contact_id':resolve_contact(args.contact,args.db)}
   if args.command=='review':
    if not args.status:p.error('review requires --status')
    op['status']=args.status
   elif args.command=='note':
    if args.text is None:p.error('note requires --text')
    op['note']=args.text
   else:
    if not all([args.message,args.subject,args.body,args.revision is not None]):p.error('edit requires --message, --subject, --body and --revision')
    op.update(message_id=args.message,subject=args.subject,body=args.body,revision=args.revision)
   print(json.dumps(update(args.db,op)['summary'],indent=2))
  return 0
 except (ValueError,KeyError) as exc:print(str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
