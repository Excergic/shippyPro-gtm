import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import icp_pipeline as p

class EvidenceGates(unittest.TestCase):
    def test_domain_boundary_does_not_accept_impersonation(self):
        self.assertTrue(p.primary('https://help.allsaints.com/shipping','allsaints.com'))
        self.assertFalse(p.primary('https://allsaints.com.evil.example/shipping','allsaints.com'))
        self.assertFalse(p.primary('https://notallsaints.com/shipping','allsaints.com'))

    def test_negated_international_delivery_is_not_positive_signal(self):
        self.assertFalse(p.positive_international('We do not offer international delivery.'))
        self.assertTrue(p.positive_international('We offer international delivery to most countries.'))

    def test_role_gate_rejects_wrong_function_and_junior_title(self):
        def person(title):return {'latest_experience_title':title,'url':'https://www.linkedin.com/in/real-returned-person'}
        for title in ['Store Operations Manager','Digital Marketing Lead','Head of Digital Marketing & CRM','Omnichannel Logistics Coordinator','Faculty Lecturer']:
            self.assertFalse(p.accepted_contact(person(title)),title)
        for title in ['Head of Logistics','Supply Chain Director','Directrice eCommerce & Marketplace','CIO','IT Director, ERP Core Solutions','Chief Operating Officer']:
            self.assertTrue(p.accepted_contact(person(title)),title)

    def test_future_and_undated_events_do_not_earn_recency_points(self):
        c=json.loads((p.ROOT/'config/accounts.json').read_text())[0]
        def event(day):return {'type':'warehouse_expansion','date':day,'weight':25,'summary':'Test event','url':'https://example.com/event'}
        for day in ['2027-01-01',None,'2024-01-01']:
            row,_=p.evaluate(c,{c['domain']:[event(day)]})
            self.assertEqual(row['recent_event_score'],0)

    def test_duplicate_event_type_cannot_double_score(self):
        c=json.loads((p.ROOT/'config/accounts.json').read_text())[0]
        e={'type':'warehouse_expansion','date':'2026-10-01','weight':20,'summary':'Test','url':'https://example.com/event'}
        row,_=p.evaluate(c,{c['domain']:[e,e]})
        self.assertEqual(row['recent_event_score'],20)

    def test_live_artifact_contract(self):
        rows=p.read(p.OUT/'accounts.json')
        self.assertEqual(len(rows),100)
        self.assertEqual(len({r['company_domain'] for r in rows}),100)
        self.assertTrue(all(0<=r['score']<=100 for r in rows))
        suppressed=set(p.read(p.ROOT/'config/settings.json')['suppressed_domains'])
        self.assertFalse(suppressed.intersection(r['company_domain'] for r in rows))
        top=[r for r in rows if r['qualification_status']=='ICP_qualified'][:50]
        self.assertEqual(len(top),50)
        self.assertTrue(all(r['primary_evidence_url'] and r['source_receipts'] for r in top))
        self.assertTrue(all(r['shipment_volume']=='unknown' and r['purchase_intent']=='unknown' for r in rows))

if __name__=='__main__':unittest.main()
