CREATE TABLE manufacturers (
 manufacturer_id INTEGER PRIMARY KEY, canonical_name TEXT NOT NULL,
 canonical_key TEXT NOT NULL UNIQUE CHECK(length(trim(canonical_key))>0)
);
CREATE TABLE manufacturer_aliases (
 alias_id INTEGER PRIMARY KEY, manufacturer_id INTEGER NOT NULL REFERENCES manufacturers,
 source_id INTEGER NOT NULL REFERENCES sources, alias_key TEXT NOT NULL,
 original_example TEXT, approved_by TEXT NOT NULL, approved_at TEXT NOT NULL, reason TEXT NOT NULL,
 UNIQUE(source_id,alias_key)
);
CREATE TABLE countries (
 country_id INTEGER PRIMARY KEY, country_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL
);
ALTER TABLE sites ADD COLUMN country_id INTEGER REFERENCES countries;
ALTER TABLE loads ADD COLUMN snapshot_at TEXT;
ALTER TABLE loads ADD COLUMN sheet_name TEXT;
ALTER TABLE loads ADD COLUMN importer_version TEXT;
ALTER TABLE categories ADD COLUMN category_code TEXT;
ALTER TABLE categories ADD COLUMN status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','inactive'));
CREATE UNIQUE INDEX category_code_unique ON categories(category_code) WHERE category_code IS NOT NULL;
CREATE TABLE families (
 family_id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories,
 family_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, UNIQUE(category_id,name)
);
CREATE TRIGGER family_root_insert BEFORE INSERT ON families
WHEN EXISTS(SELECT 1 FROM categories WHERE category_id=NEW.category_id AND parent_id IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'Una familia debe pertenecer a una categoria raiz'); END;
CREATE TRIGGER family_root_update BEFORE UPDATE OF category_id ON families
WHEN EXISTS(SELECT 1 FROM categories WHERE category_id=NEW.category_id AND parent_id IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'Una familia debe pertenecer a una categoria raiz'); END;
CREATE TRIGGER category_stays_root BEFORE UPDATE OF parent_id ON categories
WHEN NEW.parent_id IS NOT NULL AND EXISTS(SELECT 1 FROM families WHERE category_id=OLD.category_id)
BEGIN SELECT RAISE(ABORT,'Categoria con familias debe seguir siendo raiz'); END;
ALTER TABLE master_products ADD COLUMN manufacturer_id INTEGER REFERENCES manufacturers;
ALTER TABLE master_products ADD COLUMN family_id INTEGER REFERENCES families;
ALTER TABLE inventory_snapshots ADD COLUMN bin_location TEXT;
ALTER TABLE inventory_snapshots ADD COLUMN shelf_location TEXT;
ALTER TABLE inventory_snapshots ADD COLUMN maximum_qty TEXT;
ALTER TABLE inventory_snapshots ADD COLUMN minimum_qty TEXT;
ALTER TABLE inventory_snapshots ADD COLUMN reorder_qty TEXT;
ALTER TABLE inventory_snapshots ADD COLUMN affects_availability INTEGER CHECK(affects_availability IN (0,1));
ALTER TABLE inventory_snapshots ADD COLUMN is_freight INTEGER CHECK(is_freight IN (0,1));
ALTER TABLE inventory_snapshots ADD COLUMN is_misc_item INTEGER CHECK(is_misc_item IN (0,1));
CREATE TABLE snapshot_commercial (
 snapshot_id INTEGER PRIMARY KEY REFERENCES inventory_snapshots,
 cost TEXT, replacement_cost TEXT, reported_total_cost TEXT, retail_price TEXT,
 low_retail_price TEXT, msrp TEXT, currency_code TEXT
);
CREATE TABLE classification_values (
 value_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources,
 field_name TEXT NOT NULL CHECK(field_name IN ('Availability Group','Report Group','DEPARTMENT','REVENUEGROUP','EXCHANGEGROUP','INVENTORYGROUP','ACCUMULATEDDEPRECIATIONGLCODE','WRITEOFFGLCODE','COGSGROUP','TAXGROUP','DEPRCIATIONGLCODE','DISCOUNTGROUP','SUBRENTGLCODE','SELLGLCODE','Price Group')),
 raw_value TEXT NOT NULL CHECK(length(trim(raw_value))>0),
 UNIQUE(source_id,field_name,raw_value), UNIQUE(value_id,field_name)
);
CREATE TABLE record_classifications (
 raw_record_id INTEGER NOT NULL REFERENCES raw_records,
 field_name TEXT NOT NULL, value_id INTEGER NOT NULL,
 PRIMARY KEY(raw_record_id,field_name),
 FOREIGN KEY(value_id,field_name) REFERENCES classification_values(value_id,field_name)
);
CREATE TRIGGER record_classification_source_insert BEFORE INSERT ON record_classifications
WHEN (SELECT source_id FROM classification_values WHERE value_id=NEW.value_id) <>
 (SELECT l.source_id FROM raw_records r JOIN loads l USING(load_id) WHERE r.raw_record_id=NEW.raw_record_id)
BEGIN SELECT RAISE(ABORT,'Clasificacion de otra fuente'); END;
CREATE TRIGGER record_classification_source_update BEFORE UPDATE ON record_classifications
WHEN (SELECT source_id FROM classification_values WHERE value_id=NEW.value_id) <>
 (SELECT l.source_id FROM raw_records r JOIN loads l USING(load_id) WHERE r.raw_record_id=NEW.raw_record_id)
BEGIN SELECT RAISE(ABORT,'Clasificacion de otra fuente'); END;
CREATE TABLE snapshot_classifications (
 snapshot_id INTEGER NOT NULL REFERENCES inventory_snapshots,
 field_name TEXT NOT NULL, value_id INTEGER NOT NULL,
 PRIMARY KEY(snapshot_id,field_name),
 FOREIGN KEY(value_id,field_name) REFERENCES classification_values(value_id,field_name)
);
CREATE TABLE units(unit_id INTEGER PRIMARY KEY,symbol TEXT NOT NULL UNIQUE,dimension TEXT NOT NULL);
CREATE TABLE attribute_definitions (
 attribute_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,name TEXT NOT NULL,
 data_type TEXT NOT NULL CHECK(data_type IN ('text','decimal','boolean')),dimension TEXT
);
CREATE TABLE attribute_units (
 attribute_id INTEGER REFERENCES attribute_definitions,unit_id INTEGER REFERENCES units,
 PRIMARY KEY(attribute_id,unit_id)
);
CREATE TABLE family_attributes (
 family_id INTEGER REFERENCES families,attribute_id INTEGER REFERENCES attribute_definitions,
 required_for_approval INTEGER NOT NULL DEFAULT 0 CHECK(required_for_approval IN (0,1)),display_order INTEGER,
 PRIMARY KEY(family_id,attribute_id)
);
CREATE TABLE product_attribute_values (
 master_id INTEGER NOT NULL REFERENCES master_products,attribute_id INTEGER NOT NULL REFERENCES attribute_definitions,
 unit_id INTEGER,value_text TEXT,value_decimal TEXT,value_boolean INTEGER CHECK(value_boolean IN (0,1)),
 source_raw_record_id INTEGER REFERENCES raw_records,evidence_text TEXT,
 review_status TEXT NOT NULL CHECK(review_status IN ('draft','approved','rejected')),
 author TEXT NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(master_id,attribute_id),
 FOREIGN KEY(attribute_id,unit_id) REFERENCES attribute_units,
 CHECK((value_text IS NOT NULL)+(value_decimal IS NOT NULL)+(value_boolean IS NOT NULL)=1)
);
CREATE TRIGGER attribute_type_insert BEFORE INSERT ON product_attribute_values
WHEN (SELECT data_type FROM attribute_definitions WHERE attribute_id=NEW.attribute_id) <>
 CASE WHEN NEW.value_text IS NOT NULL THEN 'text' WHEN NEW.value_decimal IS NOT NULL THEN 'decimal' ELSE 'boolean' END
BEGIN SELECT RAISE(ABORT,'Tipo de atributo incorrecto'); END;
CREATE TRIGGER attribute_type_update BEFORE UPDATE ON product_attribute_values
WHEN (SELECT data_type FROM attribute_definitions WHERE attribute_id=NEW.attribute_id) <>
 CASE WHEN NEW.value_text IS NOT NULL THEN 'text' WHEN NEW.value_decimal IS NOT NULL THEN 'decimal' ELSE 'boolean' END
BEGIN SELECT RAISE(ABORT,'Tipo de atributo incorrecto'); END;
CREATE TABLE standardization_rules (
 rule_id INTEGER PRIMARY KEY,rule_key TEXT NOT NULL,version TEXT NOT NULL,input_field TEXT,
 condition_json TEXT CHECK(condition_json IS NULL OR json_valid(condition_json)),output_field TEXT,
 proposed_output TEXT,status TEXT NOT NULL CHECK(status IN ('draft','approved','inactive')),
 approved_by TEXT,approved_at TEXT,UNIQUE(rule_key,version)
);
CREATE TABLE field_standardization_proposals (
 proposal_id INTEGER PRIMARY KEY,raw_record_id INTEGER NOT NULL REFERENCES raw_records,
 rule_id INTEGER NOT NULL REFERENCES standardization_rules,target_field TEXT NOT NULL,proposed_value TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),reviewer TEXT,reason TEXT,
 UNIQUE(raw_record_id,rule_id,target_field)
);
INSERT INTO schema_version(version) VALUES(4);

