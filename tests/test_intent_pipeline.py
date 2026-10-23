"""Gate regression cases only; test fixtures are never exported as prospects."""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import intent_pipeline as p

class IntentGate(unittest.TestCase):
    def setUp(self):
        self.asof=date(2026,10,21)
        self.claim={'signal_class':'open_rfp','identity_verified':True,'icp_verified':True,'parcel_software_scope':True,
          'buyer_attributed':True,'open_opportunity_verified':True,'opportunity_state':'open_rfp',
          'already_selected_vendor':False,'publication_date':'2026-10-01','deadline':'2026-11-01',
          'status_verified_at':'2026-10-21','source_url':'https://buyer.example/rfp','buyer_or_owner':'Procurement Director',
          'project_quote':'seeks proposals for a parcel shipping platform','open_status_quote':'Responses accepted until November 1, 2026'}
        self.source={'url':self.claim['source_url'],'result':{'content':[{'type':'text','text':'Content type: text/html; Total lines: 20\nL1: Buyer seeks proposals for a parcel shipping platform.\nL2: Responses accepted until November 1, 2026.'}]}}

    def test_full_gate_accepts_documented_open_project(self):
        score,reasons=p.qualify(self.claim,self.asof,self.source)
        self.assertGreaterEqual(score,90);self.assertEqual(reasons,[])

    def test_every_required_gate_is_enforced(self):
        for key in ['identity_verified','icp_verified','parcel_software_scope','buyer_attributed','open_opportunity_verified']:
            c=copy.deepcopy(self.claim);c[key]=False
            self.assertEqual(p.qualify(c,self.asof,self.source)[0],0,key)

    def test_completed_rollout_cannot_pass(self):
        c=dict(self.claim,opportunity_state='completed',already_selected_vendor=True)
        self.assertEqual(p.qualify(c,self.asof,self.source)[0],0)

    def test_expired_project_cannot_pass(self):
        c=dict(self.claim,deadline='2026-05-31')
        self.assertEqual(p.qualify(c,self.asof,self.source)[0],0)

    def test_stale_or_future_dates_cannot_pass(self):
        for fields in [{'status_verified_at':'2026-09-01'},{'publication_date':'2027-01-01'},{'publication_date':'2025-01-01','deadline':None}]:
            self.assertEqual(p.qualify(dict(self.claim,**fields),self.asof,self.source)[0],0)

    def test_snippet_or_fabricated_quote_cannot_pass(self):
        self.assertEqual(p.qualify(self.claim,self.asof,None)[0],0)
        self.assertEqual(p.qualify(dict(self.claim,project_quote='we are replacing ShipStation'),self.asof,self.source)[0],0)

    def test_hiring_and_fit_do_not_earn_intent_points(self):
        for signal in ['generic_icp_fit','logistics_hiring','warehouse_expansion','completed_rollout','supplier_case_study']:
            self.assertEqual(p.qualify(dict(self.claim,signal_class=signal),self.asof,self.source)[0],0)

    def test_live_output_has_no_padded_qualifications(self):
        data=p.read(p.OUT/'accounts.json');summary=p.read(p.OUT/'summary.json')
        self.assertEqual(len(data),100)
        self.assertEqual(sum(r['intent_qualified'] for r in data),summary['intent_qualified_accounts'])
        self.assertEqual(summary['qualification_shortfall'],50-summary['intent_qualified_accounts'])
        self.assertTrue(all(r['supported_intent_score']==0 for r in data if not r['intent_qualified']))
        self.assertTrue(all(r['research_receipt'] for r in data))

if __name__=='__main__':unittest.main()
