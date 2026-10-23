"""Exploratory account-fit rules; no predictive validation or purchase probabilities."""
import json,re,datetime
from pathlib import Path

def signal_window(event_date, as_of, maximum_days=365):
 if not event_date:return 'date needs verification', None
 try: age=(datetime.date.fromisoformat(as_of)-datetime.date.fromisoformat(event_date)).days
 except ValueError:return 'date needs verification', None
 return ('current' if 0 <= age <= maximum_days else 'stale'), age

def build_assessment(config):
 root=Path(__file__).resolve().parents[1]; p=root/'results/signal_first_v3/account_profiles.json';rs=json.loads(p.read_text());today=datetime.date.fromisoformat(config['as_of'])
 suppressed=set(json.loads((root/'config/settings.json').read_text())['suppressed_domains'])
 dates={'onlinehomeshop.com':'2026-06-09','darwynnfulfillment.com':'2026-09-24','weill.com':'2026-02-18','finibyastar.com':'2026-08-10','thequalitygroup.com':'2026-04-07','rsgroup.com':'2026-10-08','hasbro.com':'2026-03-19','ae.com':'2026-07-27','tractorsupply.com':'2026-09-25','westcoastprep3pl.com':'2026-04-21','bestbuy.com':'2026-07-21','haier-europe.com':'2026-10-08','vente-unique.com':'2026-01-22','galaxus.de':'2026-03-02','expert.it':'2026-01-29','oliveyoung.co.kr':'2026-03-05','shein.com':'2026-09-10'}
 stale={'sezane.com','diy.com','duluthtrading.com'}
 reject={'kitandkaboodal.com':'Legal entity in administration; ownership and purchasing entity need verification', 'westcoastprep3pl.com':'Small 3PL; enterprise or midmarket scale not established', 'amazon.com':'Vertically integrated marketplace/carrier with own logistics technology','walmart.com':'Vertically integrated logistics platform; weak realistic sales fit','newcold.com':'Pallet cold storage rather than ecommerce parcel fulfilment','sibeg.it':'Beverage bulk distribution rather than parcel ecommerce','sabert.com':'Industrial packaging distribution; no demonstrated parcel ecommerce trigger','chronopost.fr':'Parcel carrier rather than merchant/fulfilment buyer','maersk.com':'Carrier and ShippyPro partner','nestle.com':'Production and bulk logistics signal rather than parcel ecommerce','aldi.co.uk':'Store replenishment signal; no demonstrated parcel ecommerce project','pepco.eu':'Store replenishment signal; no demonstrated parcel ecommerce project','action.com':'Store replenishment signal; no demonstrated parcel ecommerce project','dollartree.com':'Store distribution trigger without demonstrated parcel project','burlington.com':'Store-only retail distribution trigger','zalando.com':'Integrated marketplace fulfilment platform; weak realistic sales fit'}
 core={'United States','United Kingdom','Italy','France','Spain','Germany'}
 for i,r in enumerate(rs):
  d=r['domain'];pr=r['profile'];n=pr.get('employee_count') or 0;r['event_date']=r['event_date'] or dates.get(d,'');r['date_basis']='source-stated event or publication date' if r['event_date'] else 'exact event date not established; source publication timing retained'
  r['signal_class']='inferred buying signal';r['confirmed_purchase_intent']=False
  r['signal_caveat']='Business trigger suggests a relevant need; no evidence of an open ShippyPro or shipping-software evaluation.'
  if any(w in r['signal'].lower() for w in ['partnership','migration','platform','moved','automation','automated']):r['signal_caveat']+=' A vendor may already be selected for the reported project; complementary shipping scope needs qualification.'
  country=pr.get('country','');geo=20 if country in core else (12 if country else 0)
  parcel=30 if any(w in r['sector'].lower() for w in ['fashion','beauty','ecommerce','apparel','toys','electronics','consumer','outdoor','department']) else 15
  vertical=20 if any(w in r['sector'].lower() for w in ['fashion','beauty','apparel','outdoor','health','toys','electronics']) else 15
  scale=20 if n>=50 else (12 if n>=10 else (5 if n else 0))
  integration=10 if any(w in (r['signal']+' '+pr.get('description','')).lower() for w in ['international','europe','cross-border','omnichannel','multibrand','network','ecommerce','e-commerce']) else 5
  r.update(fit_geography=geo,fit_parcels=parcel,fit_vertical=vertical,fit_scale=scale,fit_complexity=integration,icp_score=geo+parcel+vertical+scale+integration,annual_shipments=None,scale_basis='Provider-reported headcount is a size proxy; shipment volume unverified',profile_status='provider profile found' if pr else 'provider lookup missed',exclusion_reason=reject.get(d,''))
  if d in reject:r['icp_score']=min(r['icp_score'],35)
  if d in stale:r['signal_status']='stale';r['exclusion_reason']=r['exclusion_reason'] or 'Discovered logistics source is older than 365 days'
  elif r['event_date']:
   r['signal_status'],r['signal_age_days']=signal_window(r['event_date'],config['as_of'],config['max_signal_age_days'])
  else:r['signal_status']='date needs verification'
  r['qualification']='qualified' if r['icp_score']>=70 and not r['exclusion_reason'] and pr and r['signal_status']=='current' else 'review' if not r['exclusion_reason'] else 'excluded'
  r['signal_strength']=35 if any(w in r['signal'].lower() for w in ['fulfilment','fulfillment','ecommerce launch','shipping barriers','ship-from-store','logistics hub']) else 25
  if r.get('signal_age_days',0)>180:r['signal_strength']-=10
  if r['signal_status']=='date needs verification':r['signal_strength']-=10
  if d=='weill.com': r['icp_score']-=15;r['financial_caveat']='Registry reports a recovery plan; budget authority needs verification'
  r['priority_score']=round(r['icp_score']*.7+r['signal_strength']*.3/40*100,1)
  if not pr:r['icp_score']=None;r['priority_score']=None;r['qualification']='review';r['miss_reason']='Provider company profile unresolved'
  if d in suppressed:r['qualification']='excluded';r['exclusion_reason']='Known ShippyPro customer suppression'
  r['scoring_state']='exploratory_end_to_end';r['model_version']='signal-first-v3';r['observed_at']=config['as_of']
 rs.sort(key=lambda r:(r['qualification']=='qualified',r['signal_status']=='current',r['priority_score'] if r['priority_score'] is not None else -1),reverse=True)
 for i,r in enumerate(rs,1):r['rank']=i
 (root/'results/signal_first_v3/scored_accounts.json').write_text(json.dumps(rs,indent=2))

if __name__=="__main__":
 build_assessment(json.loads((Path(__file__).resolve().parents[1]/"config/signal_first.json").read_text()))
