CREATE TABLE IF NOT EXISTS candidate_reviews (
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    code_a TEXT NOT NULL,
    code_b TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('equivalent','separate','pending')),
    reason TEXT NOT NULL CHECK(length(trim(reason))>0),
    actor TEXT NOT NULL CHECK(length(trim(actor))>0),
    updated_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(source_id,code_a,code_b),
    CHECK(code_a < code_b)
);
INSERT OR IGNORE INTO schema_version(version) VALUES(3);
