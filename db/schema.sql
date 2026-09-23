PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    installed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sources (
    source_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS loads (
    load_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','valid','rejected')),
    row_count INTEGER NOT NULL CHECK(row_count >= 0),
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    validation_notes TEXT,
    UNIQUE(source_id, sha256),
    UNIQUE(source_id, load_id)
);

CREATE TABLE IF NOT EXISTS active_loads (
    source_id INTEGER PRIMARY KEY REFERENCES sources(source_id),
    load_id INTEGER NOT NULL UNIQUE,
    FOREIGN KEY(source_id, load_id) REFERENCES loads(source_id, load_id)
);

CREATE TRIGGER IF NOT EXISTS active_load_valid_insert
BEFORE INSERT ON active_loads
WHEN NOT EXISTS(SELECT 1 FROM loads WHERE load_id=NEW.load_id AND status='valid')
BEGIN SELECT RAISE(ABORT,'La carga vigente debe estar validada'); END;
CREATE TRIGGER IF NOT EXISTS active_load_valid_update
BEFORE UPDATE ON active_loads
WHEN NOT EXISTS(SELECT 1 FROM loads WHERE load_id=NEW.load_id AND status='valid')
BEGIN SELECT RAISE(ABORT,'La carga vigente debe estar validada'); END;
CREATE TRIGGER IF NOT EXISTS keep_active_load_valid
BEFORE UPDATE OF status ON loads
WHEN NEW.status <> 'valid' AND EXISTS(SELECT 1 FROM active_loads WHERE load_id=OLD.load_id)
BEGIN SELECT RAISE(ABORT,'No se puede invalidar una carga vigente'); END;

CREATE TABLE IF NOT EXISTS raw_records (
    raw_record_id INTEGER PRIMARY KEY,
    load_id INTEGER NOT NULL REFERENCES loads(load_id),
    excel_row INTEGER NOT NULL CHECK(excel_row >= 2),
    raw_json TEXT NOT NULL CHECK(json_valid(raw_json)),
    validation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(validation_status IN ('pending','accepted','quarantined')),
    validation_reason TEXT,
    UNIQUE(load_id, excel_row),
    UNIQUE(raw_record_id, load_id)
);

CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES categories(category_id),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    CHECK(parent_id IS NULL OR parent_id <> category_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS category_root_name ON categories(name) WHERE parent_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS category_child_name ON categories(parent_id,name) WHERE parent_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS master_products (
    master_id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_code TEXT GENERATED ALWAYS AS (printf('PRD-%06d',master_id)) VIRTUAL,
    standard_name TEXT NOT NULL CHECK(length(trim(standard_name)) > 0),
    product_type TEXT NOT NULL CHECK(product_type IN ('ITEM','MISCCHARGE','LABOR','PARTS')),
    manufacturer TEXT,
    model TEXT,
    category_id INTEGER REFERENCES categories(category_id),
    package_type TEXT CHECK(package_type IN ('ITEM','PACKAGE')),
    serialization TEXT CHECK(serialization IN ('SERIAL','NONSERIAL')),
    origin TEXT NOT NULL CHECK(origin IN ('import','manual')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by TEXT NOT NULL,
    creation_reason TEXT NOT NULL CHECK(length(trim(creation_reason)) > 0)
);

CREATE TABLE IF NOT EXISTS legacy_products (
    legacy_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    legacy_code TEXT NOT NULL CHECK(length(trim(legacy_code)) > 0),
    UNIQUE(source_id, legacy_code),
    UNIQUE(legacy_id, source_id)
);

CREATE TABLE IF NOT EXISTS product_mappings (
    legacy_id INTEGER PRIMARY KEY REFERENCES legacy_products(legacy_id),
    master_id INTEGER NOT NULL REFERENCES master_products(master_id),
    method TEXT NOT NULL CHECK(method IN ('initial','reviewed')),
    reason TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS sites (
    site_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    source_site_code TEXT NOT NULL CHECK(length(trim(source_site_code)) > 0),
    name TEXT NOT NULL,
    UNIQUE(source_id, source_site_code),
    UNIQUE(site_id, source_id)
);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    load_id INTEGER NOT NULL,
    raw_record_id INTEGER NOT NULL UNIQUE,
    legacy_id INTEGER NOT NULL,
    site_id INTEGER NOT NULL,
    stock TEXT,
    cost TEXT,
    replacement_cost TEXT,
    currency TEXT,
    can_rent INTEGER CHECK(can_rent IN (0,1)),
    can_sell INTEGER CHECK(can_sell IN (0,1)),
    can_subrent INTEGER CHECK(can_subrent IN (0,1)),
    FOREIGN KEY(source_id, load_id) REFERENCES loads(source_id, load_id),
    FOREIGN KEY(raw_record_id, load_id) REFERENCES raw_records(raw_record_id, load_id),
    FOREIGN KEY(legacy_id, source_id) REFERENCES legacy_products(legacy_id, source_id),
    FOREIGN KEY(site_id, source_id) REFERENCES sites(site_id, source_id),
    UNIQUE(load_id, legacy_id, site_id)
);

CREATE TABLE IF NOT EXISTS manual_site_entries (
    entry_id INTEGER PRIMARY KEY,
    master_id INTEGER NOT NULL REFERENCES master_products(master_id),
    site_id INTEGER NOT NULL REFERENCES sites(site_id),
    stock TEXT,
    can_rent INTEGER CHECK(can_rent IN (0,1)),
    can_sell INTEGER CHECK(can_sell IN (0,1)),
    can_subrent INTEGER CHECK(can_subrent IN (0,1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','reconciled','inactive')),
    created_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS manual_site_active ON manual_site_entries(master_id,site_id) WHERE status='active';

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id INTEGER PRIMARY KEY,
    master_a INTEGER NOT NULL REFERENCES master_products(master_id),
    master_b INTEGER NOT NULL REFERENCES master_products(master_id),
    decision TEXT NOT NULL CHECK(decision IN ('link','keep_separate')),
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK(master_a < master_b)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT CHECK(before_json IS NULL OR json_valid(before_json)),
    after_json TEXT CHECK(after_json IS NULL OR json_valid(after_json)),
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE VIEW IF NOT EXISTS current_inventory AS
SELECT i.*, m.master_id
FROM inventory_snapshots i
JOIN active_loads a ON a.source_id=i.source_id AND a.load_id=i.load_id
LEFT JOIN product_mappings m ON m.legacy_id=i.legacy_id;

CREATE VIEW IF NOT EXISTS current_catalog AS
SELECT p.* FROM master_products p
WHERE p.status='active' AND (p.origin='manual' OR EXISTS (
    SELECT 1 FROM current_inventory i WHERE i.master_id=p.master_id
));

CREATE VIEW IF NOT EXISTS manual_import_overlaps AS
SELECT e.entry_id, e.master_id, e.site_id, i.snapshot_id
FROM manual_site_entries e JOIN current_inventory i
ON e.master_id=i.master_id AND e.site_id=i.site_id
WHERE e.status='active';

INSERT OR IGNORE INTO schema_version(version) VALUES(1);
INSERT OR IGNORE INTO sources(name) VALUES('RLA_Productos');
