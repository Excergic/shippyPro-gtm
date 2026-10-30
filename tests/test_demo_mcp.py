"""Demo workspace, buying-committee roles and the MCP tools; all writes use temporary databases."""
import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import buying_committee as bc
import demo
import mcp_server as mcp
import outbound_engine as engine


class Committee(unittest.TestCase):
 def test_titles_map_to_roles(self):
  for title,role in [('COO','executive'),('Vice President Supply Chain','executive'),('Founder / CEO','executive'),('Head of Logistics','end_user'),
                     ('Head of eCommerce and Digital','end_user'),('Director of Operations','end_user'),('Chief Technology Officer','technical'),
                     ('SVP E-Commerce & Digital (Chief Digital Officer)','technical'),('Head of Integration','technical'),('',  'end_user')]:
   self.assertEqual(bc.classify(title),role,title)
 def test_coverage_reports_missing_roles(self):
  k=bc.coverage([dict(domain='a',company='A',title='COO'),dict(domain='a',company='A',title='CTO'),dict(domain='b',company='B',title='Head of Logistics')])
  self.assertEqual(k['multi_threaded_accounts'],1);self.assertEqual(k['by_role'],{'executive':1,'end_user':1,'technical':1})
  self.assertEqual(next(r for r in k['rows'] if r['domain']=='b')['missing'],['executive','technical'])
 def test_touches_two_and_three_follow_the_role(self):
  rows=[dict(r,job_title=t) for r,t in zip(engine.read(demo.SAMPLE)[:1]*3,['COO','Head of Logistics','CTO'])]
  bodies=[engine.drafts(r,r['angle'],demo.config()) for r in rows]
  for (key,role),d in zip(bc.ROLES.items(),bodies):
   self.assertIn(role['touch_2'],d[1]['body']);self.assertIn(role['touch_3'],d[2]['body']);self.assertEqual(d[0]['committee_role'],key)
   for m in d:self.assertFalse(engine.qa_message(m))


class DemoAndMcp(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();out=Path(self.tmp.name)
  self.built=demo.build(out)
  self.patches=[patch.object(mcp,'CAMPAIGN',out/'campaign.sqlite3'),patch.object(mcp,'LEADS',out/'leads.sqlite3'),patch.object(mcp,'DEMO',True)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in self.patches:p.stop()
  self.tmp.cleanup()
 def test_demo_build_is_complete_and_never_touches_real_outputs(self):
  self.assertEqual(self.built['accounts'],5)
  s=engine.state(mcp.CAMPAIGN);self.assertEqual(s['summary']['draft_messages'],20);self.assertEqual(s['summary']['linkedin_draft_messages'],20)
  self.assertTrue(all(c['domain'].endswith('.example') for c in s['contacts']))
  self.assertEqual(set(s['committee']['by_role'].values())-{0},{1,2})
 def test_top_accounts_filters_by_signal_text_and_country(self):
  rows=mcp.get_top_scored_accounts(shipping_signal='DHL',country='Germany')
  self.assertEqual([r['company_name'] for r in rows],['Northwind Outdoor','Fjord Pet Supply'])
  self.assertTrue(all(r['contact_id'] for r in rows));self.assertNotIn('email',rows[0])
  self.assertEqual(mcp.get_top_scored_accounts(min_score=90)[0]['fit_score'],95)
 def test_evidence_includes_fit_breakdown_and_drafts(self):
  e=mcp.inspect_account_evidence('Brightwave');self.assertEqual(e['fit']['icp_score'],90);self.assertEqual(len(e['email_drafts']),4)
  self.assertEqual(e['contact']['committee']['role'],'executive');self.assertIn('error',mcp.inspect_account_evidence('no-such-company'))
 def test_update_rewrites_one_touch_and_keeps_audit_trail(self):
  r=mcp.update_draft_status('lumen-skincare.example',2,new_copy='Hi Alex,\n\nRewritten for the technical evaluator.',status='needs_revision')
  self.assertEqual((r['touch']['revision'],r['touch']['edited'],r['review_status'],r['sent']),(2,1,'needs_revision',False))
  counts=engine.state(mcp.CAMPAIGN)['event_counts'];self.assertEqual(counts['draft_edited'],1);self.assertEqual(counts['audit_review_changed'],1)
  with self.assertRaises(ValueError):mcp.update_draft_status('lumen-skincare.example',1,status='sent')
 def test_stdio_protocol(self):
  lines=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},{'jsonrpc':'2.0','method':'notifications/initialized'},
         {'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'update_draft_status','arguments':{'contact_id':'nobody','touch_number':1}}},
         {'jsonrpc':'2.0','id':4,'method':'resources/list'}]
  out=io.StringIO()
  with patch.object(sys,'stdin',io.StringIO('\n'.join(json.dumps(l) for l in lines)+'\n')),patch.object(sys,'stdout',out):mcp.main()
  replies=[json.loads(l) for l in out.getvalue().splitlines()]
  self.assertEqual([r['id'] for r in replies],[1,2,3,4])
  self.assertEqual({t['name'] for t in replies[1]['result']['tools']},{'get_top_scored_accounts','inspect_account_evidence','update_draft_status'})
  self.assertTrue(replies[2]['result']['isError']);self.assertEqual(replies[3]['error']['code'],-32601)


if __name__=='__main__':unittest.main()
