import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import outbound_engine
from shippypro_db import sync, SCOPE
from lead_store import LeadStore


class ShippyProDatabaseTests(unittest.TestCase):
    def test_original_results_persist_without_duplicates_or_fake_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'leads.sqlite3'
            campaign = outbound_engine.state()
            sync(campaign, db)
            store = LeadStore(db)
            raw = store.rows(SCOPE, 'raw_leads')
            usable = store.rows(SCOPE, 'usable_leads')
            self.assertEqual(len(raw), 100)
            self.assertEqual(len(usable), 50)
            self.assertEqual(sum(len(json.loads(row['messages_json'])) for row in usable), 200)
            self.assertTrue(all(row['email_status'] != 'verified' and row['last_verified_at'] is None for row in usable))
            sync(campaign, db)
            self.assertEqual(len(store.rows(SCOPE, 'raw_leads')), 100)
            self.assertEqual(len(store.rows(SCOPE, 'usable_leads')), 50)
            with store.connection() as connection:
                self.assertFalse(connection.execute('PRAGMA foreign_key_check').fetchall())
                self.assertEqual(connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0], 2)

    def test_review_and_edit_are_reflected_in_the_lead_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'leads.sqlite3'
            campaign = outbound_engine.state()
            first = campaign['contacts'][0]
            first['note'] = 'Check the project owner'
            first['review_status'] = 'needs_revision'
            first['messages'][0]['body'] = 'A manually edited audit draft'
            sync(campaign, db)
            row = next(r for r in LeadStore(db).rows(SCOPE, 'usable_leads') if r['website'] == first['domain'])
            details = json.loads(row['enrichment_data_json'])
            self.assertEqual(details['note'], 'Check the project owner')
            self.assertEqual(details['review_status'], 'needs_revision')
            self.assertEqual(json.loads(row['messages_json'])[0]['body'], 'A manually edited audit draft')


if __name__ == '__main__':
    unittest.main()
