"""Independent safety/lineage assertions on the real signal-first run."""
import csv,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import signal_pipeline as p
from signal_assessment import signal_window
class SignalFirst(unittest.TestCase):
 def test_window_rejects_future_stale_unknown_and_malformed(self):
  self.assertEqual(signal_window('2026-10-23','2026-10-22')[0],'stale')
  self.assertEqual(signal_window('2025-10-21','2026-10-22')[0],'stale')
  self.assertEqual(signal_window('2025-10-22','2026-10-22')[0],'current')
  for v in ['', 'not-a-date']:self.assertEqual(signal_window(v,'2026-10-22')[0],'date needs verification')
 def test_unrelated_roles_never_enter_contact_export(self):
  for title in ['Director HR Operations','Senior Director Regional Marketing, Digital Games','Head of Digital Marketing','Head of Talent Acquisition Technology','Project Logistics Manager','Key Account Manager - Ecommerce']:
   self.assertFalse(p.eligible(dict(latest_experience_title=title,url='https://www.linkedin.com/in/public-profile')),title)
  for title in ['Chief Supply Chain Officer','SVP Operations','Director of Global Ecommerce']:
   self.assertTrue(p.eligible(dict(latest_experience_title=title,url='https://www.linkedin.com/in/public-profile')),title)
 def test_email_null_empty_and_pending_not_fabricated(self):
  for value in [None, '{}','{"Work Email": null}']:
   self.assertEqual(p.email_value({'enrichments':[{'name':'Work Email','state':'completed','value':value}]}),('',False))
  self.assertEqual(p.email_value({'enrichments':[{'name':'Email','state':'in-progress','value':None}]}),('',True))
 def test_full_cohort_has_source_first_lineage(self):
  candidates=p.read(p.OUT/'signal_candidates.json');sources={s['id']:s for s in p.read(p.OUT/'source_catalog.json')}
  self.assertEqual(len(candidates),100);self.assertEqual(len({r['domain'] for r in candidates}),100)
  for r in candidates:
   self.assertEqual(r['source_url'],sources[r['source_id']]['url'])
   self.assertTrue((ROOT/r['receipt']).exists())
 def test_live_delivery_counts_and_honest_intent_labels(self):
  selected=p.read(p.OUT/'selected_accounts.json');summary=p.read(p.OUT/'summary.json')
  self.assertEqual(len(selected),50);self.assertEqual(len({r['domain'] for r in selected}),50)
  for r in selected:
   self.assertEqual(r['qualification'],'qualified');self.assertGreaterEqual(r['icp_score'],70)
   self.assertEqual(r['signal_status'],'current');self.assertFalse(r['confirmed_purchase_intent'])
   self.assertTrue(r['decision_maker']);self.assertIn('linkedin.com/in/',r['linkedin'])
  self.assertEqual(sum(bool(r['work_email']) for r in selected),summary['primary_work_emails'])
  self.assertFalse(any(r['primary_contact']['entityId'] in ['141805032','469107961','787521698'] for r in selected))
  self.assertFalse(any(r['domain'] in {'amazon.com','chronopost.fr','newcold.com','kitandkaboodal.com'} for r in selected))
 def test_contacts_do_not_change_company_qualification(self):
  # Contact enrichment only occurs after the account score and cannot promote it.
  source=(ROOT/'src/signal_assessment.py').read_text()
  self.assertNotIn('contacts',source);self.assertNotIn('config/accounts.json',source)
  all_rows=p.read(p.OUT/'scored_accounts.json');self.assertEqual(len(all_rows),100)
  self.assertTrue(all(r['icp_score'] is None for r in all_rows if not r['profile']))
if __name__=='__main__':unittest.main()
