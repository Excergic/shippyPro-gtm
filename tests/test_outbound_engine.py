"""Real-artifact and durable audit-state checks; all mutations use temporary DBs."""
import contextlib,io,json,shutil,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import outbound_engine as p
class CampaignAudit(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'campaign.sqlite3';shutil.copyfile(p.DB,self.db)
  self.export_patch=patch.object(p,'export',side_effect=lambda db=p.DB:p.state(db));self.export_patch.start()
  self.person=p.state(self.db)['contacts'][0]
 def tearDown(self):self.export_patch.stop();self.tmp.cleanup()
 def test_population_and_four_touch_contract(self):
  s=p.state(self.db);self.assertEqual(len(s['contacts']),50);ids=set()
  for c in s['contacts']:
   self.assertEqual([m['step'] for m in c['messages']],[1,2,3,4]);self.assertEqual([m['day_offset'] for m in c['messages']],[0,4,9,16])
   self.assertTrue((ROOT/c['research']['search_receipt']).exists())
   for m in c['messages']:
    self.assertNotIn(m['id'],ids);ids.add(m['id']);self.assertFalse(p.qa_message(m));self.assertIn(c['research']['company_source'],m['evidence'])
  self.assertEqual(len(ids),200)
 def test_ghost_mode_cannot_send_or_fabricate_engagement(self):
  for action in ['send','send_now','reply','meeting_booked','record_open','activate']:
   with self.assertRaises(ValueError):p.update(self.db,dict(action=action,contact_id=self.person['id']))
  self.assertEqual(p.state(self.db)['summary']['sent'],0);self.assertEqual(p.state(self.db)['summary']['replies'],0)
 def test_edit_and_note_survive_rebuild_without_becoming_reviewed(self):
  c=self.person;m=c['messages'][0]
  p.update(self.db,dict(action='review',contact_id=c['id'],status='reviewed',event_id='review-once'))
  p.update(self.db,dict(action='note',contact_id=c['id'],note='Verify the operational owner before use',event_id='note-once'))
  op=dict(action='edit_message',contact_id=c['id'],message_id=m['id'],revision=m['revision'],subject='A reviewed operational question',body=m['body']+'\n\nAudit edit.',event_id='edit-once')
  p.update(self.db,op)
  with contextlib.redirect_stdout(io.StringIO()):p.build(self.db)
  after=p.state(self.db)['contacts'][0]
  self.assertIn('Audit edit.',after['messages'][0]['body']);self.assertEqual(after['note'],'Verify the operational owner before use');self.assertEqual(after['review_status'],'unreviewed')
 def test_retries_are_idempotent_and_conflicting_ids_fail(self):
  c=self.person;m=c['messages'][0];op=dict(action='edit_message',contact_id=c['id'],message_id=m['id'],revision=m['revision'],subject='Check the parcel workflow',body=m['body'],event_id='stable-request')
  first=p.update(self.db,op);second=p.update(self.db,op)
  self.assertEqual(first['contacts'][0]['messages'][0]['revision'],second['contacts'][0]['messages'][0]['revision'])
  self.assertEqual(second['event_counts'].get('draft_edited'),1)
  with self.assertRaises(ValueError):p.update(self.db,dict(op,subject='Different operation'))
 def test_stale_revision_cannot_overwrite_a_newer_edit(self):
  c=self.person;m=c['messages'][0];op=dict(action='edit_message',contact_id=c['id'],message_id=m['id'],revision=m['revision'],subject='First version',body=m['body'])
  p.update(self.db,op)
  with self.assertRaises(ValueError):p.update(self.db,dict(op,subject='Stale version'))
 def test_rebuild_does_not_duplicate_campaign_or_events(self):
  before=p.state(self.db)
  with contextlib.redirect_stdout(io.StringIO()):p.build(self.db)
  after=p.state(self.db);self.assertEqual(before['event_counts'],after['event_counts']);self.assertEqual(after['summary']['draft_messages'],200)
 def test_role_and_region_conflicts_remain_visible(self):
  rows={c['domain']:c for c in p.state(self.db)['contacts']}
  self.assertTrue(any('Latin America' in f for f in rows['shein.com']['research']['review_flags']))
  self.assertTrue(any('VP title' in f for f in rows['levistrauss.com']['research']['review_flags']))
  self.assertEqual(rows['nfiindustries.com']['research']['research_status'],'provider_context_only_after_public_search')
 def test_backup_import_is_portable_idempotent_and_atomic(self):
  c=self.person;m=c['messages'][0];b={'campaign_id':p.read(p.CFG)['campaign_id'],'contacts':{c['id']:{'note':'Portable review note','review_status':'reviewed','messages':{m['id']:{'subject':'Portable draft','body':m['body'],'base_hash':m['content_hash']}}}}}
  f=Path(self.tmp.name)/'review.json';f.write_text(json.dumps(b));p.apply_backup(f,self.db);before=p.state(self.db);p.apply_backup(f,self.db);after=p.state(self.db)
  self.assertEqual(before['event_counts'],after['event_counts']);self.assertEqual(after['contacts'][0]['note'],'Portable review note');self.assertEqual(after['contacts'][0]['review_status'],'reviewed')
  b['contacts'][c['id']]['note']='Must not partially write';b['contacts'][c['id']]['messages'][m['id']]['base_hash']='wrong-hash';f.write_text(json.dumps(b))
  with self.assertRaises(ValueError):p.apply_backup(f,self.db)
  self.assertEqual(p.state(self.db)['contacts'][0]['note'],'Portable review note')
if __name__=='__main__':unittest.main()
