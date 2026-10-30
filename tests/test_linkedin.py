import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import outbound_engine as engine
import linkedin_copy


class LinkedInDrafts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'campaign.sqlite3'
        source = sqlite3.connect(engine.DB)
        target = sqlite3.connect(self.database)
        source.backup(target)
        target.close()
        source.close()
        self.export = patch.object(engine, 'export', side_effect=lambda db=engine.DB: engine.state(db))
        self.export.start()
        self.person = engine.state(self.database)['contacts'][0]

    def tearDown(self):
        self.export.stop()
        self.temp.cleanup()

    def test_all_fifty_have_event_based_connection_and_three_followups(self):
        state = engine.state(self.database)
        self.assertEqual(state['summary']['linkedin_draft_messages'], 200)
        notes = set()
        for person in state['contacts']:
            messages = person['linkedin_messages']
            self.assertEqual([m['step'] for m in messages], [1, 2, 3, 4])
            self.assertLessEqual(len(messages[0]['body'].encode('utf-16-le')) // 2, 200)
            self.assertLess(sum(len(m['body'].split()) for m in messages), 300)
            self.assertIn('ShippyPro', messages[0]['body'])
            self.assertNotIn('http', messages[0]['body'])
            self.assertTrue(all(person['research']['company_source'] in m['evidence'] for m in messages))
            self.assertTrue(all('after acceptance' in m['timing'] for m in messages[1:]))
            notes.add(messages[0]['body'])
        self.assertEqual(len(notes), 50)
        self.assertEqual(state['summary']['sent'], 0)

    def test_linkedin_edits_are_idempotent_and_leave_email_untouched(self):
        p = self.person
        m = p['linkedin_messages'][0]
        operation = dict(action='edit_linkedin', contact_id=p['id'], message_id=m['id'],
                         revision=m['revision'], body=m['body'] + ' Thanks!', event_id='linkedin-once')
        first = engine.update(self.database, operation)
        second = engine.update(self.database, operation)
        self.assertEqual(first['contacts'][0]['linkedin_messages'], second['contacts'][0]['linkedin_messages'])
        self.assertEqual(second['contacts'][0]['messages'], p['messages'])
        self.assertEqual(second['event_counts']['linkedin_draft_edited'], 1)
        with self.assertRaises(ValueError):
            engine.update(self.database, dict(operation, event_id='another', body='A stale update'))
        with contextlib.redirect_stdout(io.StringIO()):
            engine.build(self.database)
        self.assertEqual(engine.state(self.database)['contacts'][0]['linkedin_messages'][0]['body'], operation['body'])

    def test_character_budget_and_contact_identity_are_enforced(self):
        p = self.person
        m = p['linkedin_messages'][0]
        for body in ['x' * 201, '😀' * 101]:
            with self.assertRaises(ValueError):
                engine.update(self.database, dict(action='edit_linkedin', contact_id=p['id'], message_id=m['id'], revision=m['revision'], body=body))
        other = engine.state(self.database)['contacts'][1]
        with self.assertRaises(ValueError):
            engine.update(self.database, dict(action='edit_linkedin', contact_id=other['id'], message_id=m['id'], revision=m['revision'], body='Wrong contact'))
        with self.assertRaises(ValueError):
            linkedin_copy.validate('word ' * 300, 2)

    def test_linkedin_backup_import_conflicts_do_not_partially_apply(self):
        p = self.person
        m = p['linkedin_messages'][0]
        backup = {'campaign_id': engine.read(engine.CFG)['campaign_id'], 'contacts': {p['id']: {
            'note': 'Preserve a LinkedIn review note', 'linkedin_messages': {m['id']: {'body': m['body'] + ' Thanks!', 'base_hash': m['content_hash']}}}}}
        file = Path(self.temp.name) / 'backup.json'
        file.write_text(json.dumps(backup))
        engine.apply_backup(file, self.database)
        self.assertEqual(engine.state(self.database)['contacts'][0]['note'], 'Preserve a LinkedIn review note')
        backup['contacts'][p['id']]['note'] = 'Must not apply'
        backup['contacts'][p['id']]['linkedin_messages'][m['id']]['base_hash'] = 'bad-hash'
        file.write_text(json.dumps(backup))
        with self.assertRaises(ValueError):
            engine.apply_backup(file, self.database)
        self.assertEqual(engine.state(self.database)['contacts'][0]['note'], 'Preserve a LinkedIn review note')
