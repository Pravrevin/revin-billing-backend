-- ============================================================
--  MULTI-TENANCY MIGRATION
--  Adds auth tables + a pharmacy_id tenant column to every data
--  table, backfills existing rows to a default pharmacy (id = 1),
--  and relaxes global unique constraints to be per-pharmacy.
--
--  Idempotent: safe to run on an existing DB, and also appended to
--  create_tables.sql so fresh installs get the same schema.
-- ============================================================

-- ── auth / tenancy tables ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pharmacy (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    code        VARCHAR(50) UNIQUE,
    address     VARCHAR(500),
    phone       VARCHAR(30),
    is_active   BOOLEAN DEFAULT TRUE NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_user (
    id            BIGSERIAL PRIMARY KEY,
    pharmacy_id   BIGINT REFERENCES pharmacy(id) ON DELETE CASCADE,
    username      VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(255),
    role          VARCHAR(30) NOT NULL DEFAULT 'pharmacy_user',
    is_active     BOOLEAN DEFAULT TRUE NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_app_user_pharmacy_id ON app_user (pharmacy_id);

CREATE TABLE IF NOT EXISTS user_permission (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    menu_id   INTEGER NOT NULL,
    sub_id    INTEGER,
    CONSTRAINT uq_user_menu_sub UNIQUE (user_id, menu_id, sub_id)
);
CREATE INDEX IF NOT EXISTS idx_user_permission_user_id ON user_permission (user_id);

CREATE TABLE IF NOT EXISTS menu_access_log (
    id          BIGSERIAL PRIMARY KEY,
    pharmacy_id BIGINT,
    user_id     BIGINT,
    menu_id     INTEGER NOT NULL,
    sub_id      INTEGER,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_menu_access_log_pharmacy ON menu_access_log (pharmacy_id);
CREATE INDEX IF NOT EXISTS idx_menu_access_log_user     ON menu_access_log (user_id);
CREATE INDEX IF NOT EXISTS idx_menu_access_log_time     ON menu_access_log (accessed_at);

-- Default pharmacy that legacy (pre-tenancy) data is attached to.
INSERT INTO pharmacy (id, name, code, is_active)
VALUES (1, 'Default Pharmacy', 'DEFAULT', TRUE)
ON CONFLICT (id) DO NOTHING;
-- Keep the BIGSERIAL sequence ahead of the manually inserted id=1.
SELECT setval(pg_get_serial_sequence('pharmacy', 'id'),
              GREATEST((SELECT MAX(id) FROM pharmacy), 1));

-- ── add pharmacy_id to every tenant table + backfill + NOT NULL ──────────────

DO $$
DECLARE
    t TEXT;
    tenant_tables TEXT[] := ARRAY[
        'category_master', 'sub_category_master', 'marketer_master',
        'brand_master', 'packaging_master', 'item_master', 'party_master',
        'stock_master', 'payment_mode_master', 'purchase_master',
        'purchase_items', 'sales_master', 'sales_items', 'stock_ledger',
        'party_credit_config', 'payment_master', 'expense_master',
        'sales_return_master', 'sales_return_items', 'held_bill'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS pharmacy_id BIGINT', t);
        EXECUTE format('UPDATE %I SET pharmacy_id = 1 WHERE pharmacy_id IS NULL', t);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN pharmacy_id SET NOT NULL', t);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (pharmacy_id)',
                       'idx_' || t || '_pharmacy_id', t);
    END LOOP;
END $$;

-- ── unit_master: composite PK (pharmacy_id, unit_name) ───────────────────────

ALTER TABLE unit_master ADD COLUMN IF NOT EXISTS pharmacy_id BIGINT;
UPDATE unit_master SET pharmacy_id = 1 WHERE pharmacy_id IS NULL;
ALTER TABLE unit_master ALTER COLUMN pharmacy_id SET NOT NULL;
ALTER TABLE unit_master DROP CONSTRAINT IF EXISTS unit_master_pkey;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'unit_master_pkey'
    ) THEN
        ALTER TABLE unit_master ADD CONSTRAINT unit_master_pkey
            PRIMARY KEY (pharmacy_id, unit_name);
    END IF;
END $$;

-- ── relax global unique constraints → per-pharmacy composite uniques ─────────
-- Drop the auto-named single-column unique, add a (pharmacy_id, <col>) unique.

ALTER TABLE category_master     DROP CONSTRAINT IF EXISTS category_master_category_code_key;
ALTER TABLE sub_category_master DROP CONSTRAINT IF EXISTS sub_category_master_sub_category_code_key;
ALTER TABLE marketer_master     DROP CONSTRAINT IF EXISTS marketer_master_marketer_code_key;
ALTER TABLE brand_master        DROP CONSTRAINT IF EXISTS brand_master_brand_name_key;
ALTER TABLE packaging_master    DROP CONSTRAINT IF EXISTS packaging_master_packing_type_key;
ALTER TABLE item_master         DROP CONSTRAINT IF EXISTS item_master_item_code_key;
ALTER TABLE party_master        DROP CONSTRAINT IF EXISTS party_master_party_code_key;
ALTER TABLE payment_mode_master DROP CONSTRAINT IF EXISTS payment_mode_master_mode_name_key;
ALTER TABLE party_credit_config DROP CONSTRAINT IF EXISTS party_credit_config_party_id_key;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_category_master_code') THEN
        ALTER TABLE category_master ADD CONSTRAINT uq_category_master_code UNIQUE (pharmacy_id, category_code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_sub_category_master_code') THEN
        ALTER TABLE sub_category_master ADD CONSTRAINT uq_sub_category_master_code UNIQUE (pharmacy_id, sub_category_code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_marketer_master_code') THEN
        ALTER TABLE marketer_master ADD CONSTRAINT uq_marketer_master_code UNIQUE (pharmacy_id, marketer_code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_brand_master_name') THEN
        ALTER TABLE brand_master ADD CONSTRAINT uq_brand_master_name UNIQUE (pharmacy_id, brand_name);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_packaging_master_type') THEN
        ALTER TABLE packaging_master ADD CONSTRAINT uq_packaging_master_type UNIQUE (pharmacy_id, packing_type);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_item_master_code') THEN
        ALTER TABLE item_master ADD CONSTRAINT uq_item_master_code UNIQUE (pharmacy_id, item_code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_party_master_code') THEN
        ALTER TABLE party_master ADD CONSTRAINT uq_party_master_code UNIQUE (pharmacy_id, party_code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_payment_mode_master_name') THEN
        ALTER TABLE payment_mode_master ADD CONSTRAINT uq_payment_mode_master_name UNIQUE (pharmacy_id, mode_name);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_party_credit_config_party') THEN
        ALTER TABLE party_credit_config ADD CONSTRAINT uq_party_credit_config_party UNIQUE (pharmacy_id, party_id);
    END IF;
END $$;
