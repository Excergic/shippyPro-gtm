-- ShippyPro lead workspace. Existing compatibility IDs are retained for saved data.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_leads (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    record_type TEXT NOT NULL DEFAULT 'candidate',
    company_name TEXT,
    website TEXT,
    source_url TEXT NOT NULL,
    raw_data_json TEXT NOT NULL,
    processing_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'new',
    scraped_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (campaign_id, id),
    UNIQUE (campaign_id, source_key)
);

-- One usable lead = one qualified company/contact pair for one campaign.
-- Only promote records after checking ICP fit, intent evidence and contact data.
CREATE TABLE IF NOT EXISTS usable_leads (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    raw_lead_id INTEGER NOT NULL,
    account_id TEXT NOT NULL,
    contact_id TEXT NOT NULL,
    config_version INTEGER NOT NULL,
    input_version TEXT NOT NULL,
    tier TEXT NOT NULL,
    company_name TEXT NOT NULL,
    website TEXT NOT NULL,
    industry TEXT,
    country TEXT,
    employee_count INTEGER,
    intent_signal TEXT NOT NULL,
    intent_source_url TEXT NOT NULL,
    intent_event_at TEXT,
    intent_score REAL NOT NULL CHECK (intent_score BETWEEN 0 AND 100),
    fit_score REAL NOT NULL CHECK (fit_score BETWEEN 0 AND 100),
    qualification_reason TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_title TEXT NOT NULL,
    linkedin_url TEXT,
    email TEXT,
    phone TEXT,
    email_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (email_status IN ('missing', 'unverified', 'verified', 'invalid')),
    enrichment_data_json TEXT NOT NULL DEFAULT '{}',
    messages_json TEXT NOT NULL DEFAULT '[]',
    enriched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TEXT,
    refresh_due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'needs_refresh', 'excluded')),
    FOREIGN KEY (campaign_id, raw_lead_id) REFERENCES raw_leads(campaign_id, id),
    UNIQUE (campaign_id, contact_id)
);

CREATE INDEX IF NOT EXISTS raw_leads_campaign ON raw_leads(campaign_id);
CREATE INDEX IF NOT EXISTS usable_leads_campaign ON usable_leads(campaign_id, status);
