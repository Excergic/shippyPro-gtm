"""Two lead tables; no messaging authority or ownership is duplicated here."""
import csv
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LeadStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            schema = (ROOT / 'src/simple_lead_schema.sql').read_text()
            db.executescript(schema)
            # Earlier lead-schema drafts required a verification timestamp even
            # for historical unverified data. Preserve rows while allowing null.
            if next(r for r in db.execute('PRAGMA table_info(usable_leads)') if r[1] == 'last_verified_at')[3]:
                definition = schema.split('CREATE TABLE IF NOT EXISTS usable_leads (', 1)[1].split('CREATE INDEX', 1)[0]
                db.executescript('BEGIN IMMEDIATE; CREATE TABLE usable_leads_new (' + definition +
                                 'INSERT INTO usable_leads_new SELECT * FROM usable_leads; '
                                 'UPDATE usable_leads_new SET last_verified_at=NULL WHERE email_status!=\'verified\'; '
                                 'DROP TABLE usable_leads; ALTER TABLE usable_leads_new RENAME TO usable_leads; COMMIT;')
                db.executescript(schema)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, campaign_id, key, kind, payload, source_url, name=None, website=None):
        if not campaign_id:
            raise ValueError('campaign_id is required')
        with self.connection() as db:
            db.execute('''INSERT OR IGNORE INTO raw_leads
                (campaign_id,source_key,record_type,company_name,website,source_url,raw_data_json)
                VALUES(?,?,?,?,?,?,?)''', (campaign_id, key, kind, name, website, source_url,
                                           json.dumps(payload, ensure_ascii=False)))
            return dict(db.execute('SELECT * FROM raw_leads WHERE campaign_id=? AND source_key=?',
                                   (campaign_id, key)).fetchone())

    def get(self, campaign_id, key):
        with self.connection() as db:
            row = db.execute('SELECT * FROM raw_leads WHERE campaign_id=? AND source_key=?',
                             (campaign_id, key)).fetchone()
            return dict(row) if row else None

    def mark(self, campaign_id, row_id, status, details):
        with self.connection() as db:
            count = db.execute('UPDATE raw_leads SET status=?,processing_json=? WHERE campaign_id=? AND id=?',
                               (status, json.dumps(details, ensure_ascii=False), campaign_id, row_id)).rowcount
            if not count:
                raise ValueError('Raw lead is outside the selected campaign')

    def promote(self, campaign_id, values):
        if values.get('campaign_id', campaign_id) != campaign_id:
            raise ValueError('Campaign mismatch')
        values = dict(values, campaign_id=campaign_id)
        with self.connection() as db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(usable_leads)')} - {'id'}
            if set(values) - columns:
                raise ValueError('Unknown usable lead columns')
            names = list(values)
            update = ','.join(f'{name}=excluded.{name}' for name in names if name not in ['campaign_id', 'contact_id'])
            db.execute(f'''INSERT INTO usable_leads ({','.join(names)})
                VALUES ({','.join('?' for _ in names)})
                ON CONFLICT(campaign_id,contact_id) DO UPDATE SET {update}''', [values[name] for name in names])

    def rows(self, campaign_id, table):
        if table not in ['raw_leads', 'usable_leads']:
            raise ValueError('Unknown lead table')
        with self.connection() as db:
            return [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE campaign_id=? ORDER BY id', (campaign_id,))]

    def export(self, campaign_id, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for table in ['raw_leads', 'usable_leads']:
            rows = self.rows(campaign_id, table)
            with (directory / (table + '.csv')).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['campaign_id'])
                writer.writeheader()
                for row in rows:
                    # Keep untrusted website/person text from executing as spreadsheet formulas.
                    writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
        return directory
