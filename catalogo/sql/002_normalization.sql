CREATE TABLE IF NOT EXISTS normalized_records (
    raw_record_id INTEGER PRIMARY KEY REFERENCES raw_records(raw_record_id),
    normalized_json TEXT NOT NULL CHECK(json_valid(normalized_json)),
    rules_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_issues (
    issue_id INTEGER PRIMARY KEY,
    load_id INTEGER NOT NULL REFERENCES loads(load_id),
    raw_record_id INTEGER,
    severity TEXT NOT NULL CHECK(severity IN ('error','warning')),
    field TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    FOREIGN KEY(raw_record_id,load_id) REFERENCES raw_records(raw_record_id,load_id)
);
CREATE INDEX IF NOT EXISTS issues_load ON validation_issues(load_id,severity);
INSERT OR IGNORE INTO schema_version(version) VALUES(2);
