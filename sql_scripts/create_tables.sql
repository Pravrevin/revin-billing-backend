-- ============================================================
--  Billing Software - Database Schema
--  Run this script to create all required tables
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
--  SHARED TRIGGER FUNCTION  (must be defined before any trigger uses it)
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
--  CATEGORY MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS category_master (
    id            BIGSERIAL PRIMARY KEY,
    category_code VARCHAR(50)  UNIQUE NOT NULL,
    category_name VARCHAR(255) NOT NULL,
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_category_master_code      ON category_master (category_code);
CREATE INDEX IF NOT EXISTS idx_category_master_name      ON category_master (category_name);
CREATE INDEX IF NOT EXISTS idx_category_master_is_active ON category_master (is_active);

DROP TRIGGER IF EXISTS trg_category_master_updated_at ON category_master;
CREATE TRIGGER trg_category_master_updated_at
    BEFORE UPDATE ON category_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  SUB CATEGORY MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS sub_category_master (
    id                BIGSERIAL PRIMARY KEY,
    sub_category_code VARCHAR(50)  UNIQUE NOT NULL,
    sub_category_name VARCHAR(255) NOT NULL,
    category_id       BIGINT REFERENCES category_master(id) ON DELETE RESTRICT,
    description       TEXT,
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sub_category_master_code        ON sub_category_master (sub_category_code);
CREATE INDEX IF NOT EXISTS idx_sub_category_master_name        ON sub_category_master (sub_category_name);
CREATE INDEX IF NOT EXISTS idx_sub_category_master_category_id ON sub_category_master (category_id);
CREATE INDEX IF NOT EXISTS idx_sub_category_master_is_active   ON sub_category_master (is_active);

DROP TRIGGER IF EXISTS trg_sub_category_master_updated_at ON sub_category_master;
CREATE TRIGGER trg_sub_category_master_updated_at
    BEFORE UPDATE ON sub_category_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  MARKETER MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS marketer_master (
    id            BIGSERIAL PRIMARY KEY,
    marketer_code VARCHAR(50)  UNIQUE NOT NULL,
    marketer_name VARCHAR(255) NOT NULL,
    address       TEXT,
    city          VARCHAR(100),
    state         VARCHAR(100),
    pincode       VARCHAR(10),
    phone         VARCHAR(20),
    email         VARCHAR(100),
    gstin         VARCHAR(20),
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data    JSONB
);

CREATE INDEX IF NOT EXISTS idx_marketer_master_code      ON marketer_master (marketer_code);
CREATE INDEX IF NOT EXISTS idx_marketer_master_name      ON marketer_master (marketer_name);
CREATE INDEX IF NOT EXISTS idx_marketer_master_is_active ON marketer_master (is_active);

DROP TRIGGER IF EXISTS trg_marketer_master_updated_at ON marketer_master;
CREATE TRIGGER trg_marketer_master_updated_at
    BEFORE UPDATE ON marketer_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  BRAND MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS brand_master (
    id          BIGSERIAL PRIMARY KEY,
    brand_name  VARCHAR(255) UNIQUE NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_brand_master_brand_name ON brand_master (brand_name);
CREATE INDEX IF NOT EXISTS idx_brand_master_is_active  ON brand_master (is_active);

DROP TRIGGER IF EXISTS trg_brand_master_updated_at ON brand_master;
CREATE TRIGGER trg_brand_master_updated_at
    BEFORE UPDATE ON brand_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  UNIT MASTER  (unit_name is the primary key)
-- ============================================================
CREATE TABLE IF NOT EXISTS unit_master (
    unit_name   VARCHAR(50) PRIMARY KEY,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_unit_master_is_active ON unit_master (is_active);

DROP TRIGGER IF EXISTS trg_unit_master_updated_at ON unit_master;
CREATE TRIGGER trg_unit_master_updated_at
    BEFORE UPDATE ON unit_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  PACKAGING MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS packaging_master (
    id              BIGSERIAL PRIMARY KEY,
    packing_type    VARCHAR(50)  UNIQUE NOT NULL,
    unit_primary    VARCHAR(50),
    unit_secondary  VARCHAR(50),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_packaging_master_packing_type ON packaging_master (packing_type);
CREATE INDEX IF NOT EXISTS idx_packaging_master_is_active    ON packaging_master (is_active);

DROP TRIGGER IF EXISTS trg_packaging_master_updated_at ON packaging_master;
CREATE TRIGGER trg_packaging_master_updated_at
    BEFORE UPDATE ON packaging_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  ITEM MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS item_master (
    id                      BIGSERIAL PRIMARY KEY,
    item_code               VARCHAR(50)  UNIQUE NOT NULL,
    item_name               VARCHAR(255) NOT NULL,
    generic_name            VARCHAR(255),
    brand_name              VARCHAR(255),
    composition             TEXT,

    -- Pharmaceutical attributes
    strength                VARCHAR(50),
    dosage_form             VARCHAR(50),

    -- Category / classification — stored as names, validated against master tables
    category_name           VARCHAR(255),
    sub_category_name       VARCHAR(255),

    -- Packaging — stored as packing_type, validated against packaging_master
    packing_type            VARCHAR(50),
    pack_size               INTEGER,

    -- Unit — stored as unit_name, validated against unit_master
    unit_name               VARCHAR(50),
    conversion_factor       NUMERIC(10,2),

    -- GST / Tax
    gst_percent             NUMERIC(5,2),
    cgst                    NUMERIC(5,2),
    sgst                    NUMERIC(5,2),
    igst                    NUMERIC(5,2),
    cess_percent            NUMERIC(5,2),
    hsn_code                VARCHAR(20),
    tax_type                VARCHAR(20),      -- inclusive / exclusive

    -- Discount
    min_discount            NUMERIC(5,2),
    max_discount            NUMERIC(5,2),
    is_discount_allowed     BOOLEAN DEFAULT TRUE,

    -- Pricing
    pricing_type            VARCHAR(20),      -- MRP / RATE

    -- Stock levels
    min_stock_level         INTEGER,
    max_stock_level         INTEGER,
    reorder_level           INTEGER,

    -- Batch / Expiry tracking
    is_batch_required       BOOLEAN DEFAULT TRUE,
    is_expiry_required      BOOLEAN DEFAULT TRUE,

    -- Shelf / Lead time
    shelf_life_days         INTEGER,
    lead_time_days          INTEGER,

    -- Regulatory
    schedule_type           VARCHAR(10),      -- H, H1, X, OTC
    is_narcotic             BOOLEAN DEFAULT FALSE,
    is_psychotropic         BOOLEAN DEFAULT FALSE,
    prescription_required   BOOLEAN DEFAULT FALSE,
    drug_license_required   BOOLEAN DEFAULT FALSE,
    regulatory_category     VARCHAR(50),

    -- Codes / Identifiers
    barcode                 VARCHAR(100),
    qr_code                 TEXT,
    sku_code                VARCHAR(100),
    external_code           VARCHAR(100),

    -- Status
    is_active               BOOLEAN DEFAULT TRUE,

    -- Audit
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Extra metadata
    extra_data              JSONB
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_item_master_item_code        ON item_master (item_code);
CREATE INDEX IF NOT EXISTS idx_item_master_item_name        ON item_master (item_name);
CREATE INDEX IF NOT EXISTS idx_item_master_category_name    ON item_master (category_name);
CREATE INDEX IF NOT EXISTS idx_item_master_sub_category_name ON item_master (sub_category_name);
CREATE INDEX IF NOT EXISTS idx_item_master_packing_type     ON item_master (packing_type);
CREATE INDEX IF NOT EXISTS idx_item_master_unit_name        ON item_master (unit_name);
CREATE INDEX IF NOT EXISTS idx_item_master_is_active        ON item_master (is_active);
CREATE INDEX IF NOT EXISTS idx_item_master_hsn_code         ON item_master (hsn_code);
CREATE INDEX IF NOT EXISTS idx_item_master_barcode          ON item_master (barcode);

DROP TRIGGER IF EXISTS trg_item_master_updated_at ON item_master;
CREATE TRIGGER trg_item_master_updated_at
    BEFORE UPDATE ON item_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  PARTY MASTER  (Customer / Supplier / Both)
-- ============================================================
CREATE TABLE IF NOT EXISTS party_master (
    id                  BIGSERIAL PRIMARY KEY,
    party_code          VARCHAR(50)  UNIQUE,
    party_name          VARCHAR(255),

    party_type          VARCHAR(20),          -- Customer / Supplier / Both

    mobile              VARCHAR(20),
    email               VARCHAR(100),

    gstin               VARCHAR(20),
    drug_license_no     VARCHAR(50),

    address             TEXT,
    city                VARCHAR(100),
    state               VARCHAR(100),
    pincode             VARCHAR(10),

    credit_limit        NUMERIC(12,2),
    credit_days         INTEGER,

    opening_balance     NUMERIC(12,2),

    pan_card            VARCHAR(10),          -- Distributor only, optional
    bank_details        JSONB,                -- Distributor only, optional

    is_active           BOOLEAN DEFAULT TRUE,

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    extra_data          JSONB
);

CREATE INDEX IF NOT EXISTS idx_party_master_party_code  ON party_master (party_code);
CREATE INDEX IF NOT EXISTS idx_party_master_party_name  ON party_master (party_name);
CREATE INDEX IF NOT EXISTS idx_party_master_party_type  ON party_master (party_type);
CREATE INDEX IF NOT EXISTS idx_party_master_gstin       ON party_master (gstin);
CREATE INDEX IF NOT EXISTS idx_party_master_mobile      ON party_master (mobile);
CREATE INDEX IF NOT EXISTS idx_party_master_is_active   ON party_master (is_active);

DROP TRIGGER IF EXISTS trg_party_master_updated_at ON party_master;
CREATE TRIGGER trg_party_master_updated_at
    BEFORE UPDATE ON party_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  STOCK MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_master (
    id                  BIGSERIAL PRIMARY KEY,
    item_id             BIGINT REFERENCES item_master(id) ON DELETE RESTRICT,

    -- Batch / Dates
    batch_no            VARCHAR(50) NOT NULL,
    manufacture_date    DATE,
    expiry_date         DATE,

    -- Pricing
    mrp                 NUMERIC(10,2),
    purchase_rate       NUMERIC(10,2),
    sale_rate           NUMERIC(10,2),

    -- Quantity
    quantity            NUMERIC(10,2),
    free_quantity       NUMERIC(10,2),

    -- Location
    warehouse_id        BIGINT,
    rack_location       VARCHAR(100),

    -- Audit
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Extra metadata
    extra_data          JSONB
);

CREATE INDEX IF NOT EXISTS idx_stock_master_item_id      ON stock_master (item_id);
CREATE INDEX IF NOT EXISTS idx_stock_master_batch_no     ON stock_master (batch_no);
CREATE INDEX IF NOT EXISTS idx_stock_master_expiry_date  ON stock_master (expiry_date);
CREATE INDEX IF NOT EXISTS idx_stock_master_warehouse_id ON stock_master (warehouse_id);

DROP TRIGGER IF EXISTS trg_stock_master_updated_at ON stock_master;
CREATE TRIGGER trg_stock_master_updated_at
    BEFORE UPDATE ON stock_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  PAYMENT MODE MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS payment_mode_master (
    id          BIGSERIAL PRIMARY KEY,
    mode_name   VARCHAR(50) UNIQUE NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,

    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payment_mode_master_mode_name ON payment_mode_master (mode_name);
CREATE INDEX IF NOT EXISTS idx_payment_mode_master_is_active ON payment_mode_master (is_active);

DROP TRIGGER IF EXISTS trg_payment_mode_master_updated_at ON payment_mode_master;
CREATE TRIGGER trg_payment_mode_master_updated_at
    BEFORE UPDATE ON payment_mode_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  PURCHASE MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS purchase_master (
    id                  BIGSERIAL PRIMARY KEY,
    invoice_no          VARCHAR(50),
    invoice_date        DATE,
    entry_date          DATE,
    due_date            DATE,

    supplier_id         BIGINT REFERENCES party_master(id) ON DELETE RESTRICT,

    total_amount        NUMERIC(12,2),
    discount_percentage NUMERIC(5,2),
    discount_amount     NUMERIC(10,2),
    tax_percentage      NUMERIC(5,2),
    tax_amount          NUMERIC(10,2),
    net_amount          NUMERIC(12,2),

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    extra_data          JSONB
);

CREATE INDEX IF NOT EXISTS idx_purchase_master_invoice_no   ON purchase_master (invoice_no);
CREATE INDEX IF NOT EXISTS idx_purchase_master_invoice_date ON purchase_master (invoice_date);
CREATE INDEX IF NOT EXISTS idx_purchase_master_entry_date   ON purchase_master (entry_date);
CREATE INDEX IF NOT EXISTS idx_purchase_master_due_date     ON purchase_master (due_date);
CREATE INDEX IF NOT EXISTS idx_purchase_master_supplier_id  ON purchase_master (supplier_id);

DROP TRIGGER IF EXISTS trg_purchase_master_updated_at ON purchase_master;
CREATE TRIGGER trg_purchase_master_updated_at
    BEFORE UPDATE ON purchase_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  PURCHASE ITEMS
-- ============================================================
CREATE TABLE IF NOT EXISTS purchase_items (
    id              BIGSERIAL PRIMARY KEY,
    purchase_id     BIGINT REFERENCES purchase_master(id) ON DELETE CASCADE,

    item_id         BIGINT REFERENCES item_master(id) ON DELETE RESTRICT,
    batch_no        VARCHAR(50),

    quantity        NUMERIC(10,2),
    free_quantity   NUMERIC(10,2),

    purchase_rate   NUMERIC(10,2),
    mrp             NUMERIC(10,2),
    sale_rate       NUMERIC(10,2),

    discount        NUMERIC(10,2),
    gst_percent     NUMERIC(5,2),
    tax_amount      NUMERIC(10,2),

    expiry_date     DATE,

    total           NUMERIC(12,2)
);

CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase_id ON purchase_items (purchase_id);
CREATE INDEX IF NOT EXISTS idx_purchase_items_item_id     ON purchase_items (item_id);
CREATE INDEX IF NOT EXISTS idx_purchase_items_batch_no    ON purchase_items (batch_no);

-- ============================================================
--  SALES MASTER
-- ============================================================
CREATE TABLE IF NOT EXISTS sales_master (
    id              BIGSERIAL PRIMARY KEY,
    invoice_no      VARCHAR(50),
    invoice_date    DATE,

    customer_id     BIGINT REFERENCES party_master(id) ON DELETE RESTRICT,

    doctor_name     VARCHAR(255),

    total_amount    NUMERIC(12,2),
    discount        NUMERIC(10,2),
    tax_amount      NUMERIC(10,2),
    net_amount      NUMERIC(12,2),

    payment_mode_id BIGINT REFERENCES payment_mode_master(id) ON DELETE SET NULL,
    payment_status  VARCHAR(20),

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    extra_data      JSONB
);

CREATE INDEX IF NOT EXISTS idx_sales_master_invoice_no   ON sales_master (invoice_no);
CREATE INDEX IF NOT EXISTS idx_sales_master_invoice_date ON sales_master (invoice_date);
CREATE INDEX IF NOT EXISTS idx_sales_master_customer_id  ON sales_master (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_master_pay_status   ON sales_master (payment_status);
CREATE INDEX IF NOT EXISTS idx_sales_master_pay_mode_id  ON sales_master (payment_mode_id);

DROP TRIGGER IF EXISTS trg_sales_master_updated_at ON sales_master;
CREATE TRIGGER trg_sales_master_updated_at
    BEFORE UPDATE ON sales_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
--  SALES ITEMS
-- ============================================================
CREATE TABLE IF NOT EXISTS sales_items (
    id              BIGSERIAL PRIMARY KEY,
    sales_id        BIGINT REFERENCES sales_master(id) ON DELETE CASCADE,

    item_id         BIGINT REFERENCES item_master(id) ON DELETE RESTRICT,
    batch_no        VARCHAR(50),

    quantity        NUMERIC(10,2),

    mrp             NUMERIC(10,2),
    sale_rate       NUMERIC(10,2),

    discount        NUMERIC(10,2),
    gst_percent     NUMERIC(5,2),
    tax_amount      NUMERIC(10,2),

    expiry_date     DATE,

    total           NUMERIC(12,2)
);

CREATE INDEX IF NOT EXISTS idx_sales_items_sales_id ON sales_items (sales_id);
CREATE INDEX IF NOT EXISTS idx_sales_items_item_id  ON sales_items (item_id);
CREATE INDEX IF NOT EXISTS idx_sales_items_batch_no ON sales_items (batch_no);

-- ============================================================
--  STOCK LEDGER  (every IN / OUT movement with source reference)
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_ledger (
    id              BIGSERIAL PRIMARY KEY,
    item_id         BIGINT REFERENCES item_master(id) ON DELETE RESTRICT,
    batch_no        VARCHAR(50),

    movement_type   VARCHAR(10)  NOT NULL,   -- IN / OUT
    quantity        NUMERIC(10,2),
    free_quantity   NUMERIC(10,2),

    reference_type  VARCHAR(20),             -- purchase / sale / adjustment
    reference_id    BIGINT,                  -- purchase_master.id or sales_master.id

    purchase_rate   NUMERIC(10,2),
    mrp             NUMERIC(10,2),

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stock_ledger_item_id        ON stock_ledger (item_id);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_batch_no       ON stock_ledger (batch_no);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_movement_type  ON stock_ledger (movement_type);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_reference_type ON stock_ledger (reference_type);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_reference_id   ON stock_ledger (reference_id);

-- ============================================================
--  PARTY CREDIT CONFIG
--  Overdue rules per party (NULL party_id = global default)
-- ============================================================
CREATE TABLE IF NOT EXISTS party_credit_config (
    id                  BIGSERIAL PRIMARY KEY,

    party_id            BIGINT UNIQUE REFERENCES party_master(id) ON DELETE CASCADE,
                        -- NULL  → this row is the global default
                        -- value → override for that specific party

    credit_days         INTEGER     NOT NULL DEFAULT 30,
    overdue_grace_days  INTEGER     NOT NULL DEFAULT 0,

    created_at          TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_party_credit_config_party_id ON party_credit_config (party_id);

DROP TRIGGER IF EXISTS trg_party_credit_config_updated_at ON party_credit_config;
CREATE TRIGGER trg_party_credit_config_updated_at
    BEFORE UPDATE ON party_credit_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Seed the global default (credit_days=30, grace=0)
INSERT INTO party_credit_config (party_id, credit_days, overdue_grace_days)
VALUES (NULL, 30, 0)
ON CONFLICT DO NOTHING;

-- ============================================================
--  PAYMENT MASTER
--  Unified table for ALL money movements:
--    RECEIPT  — money received FROM a customer   (against a sales invoice)
--    PAYMENT  — money paid OUT TO a distributor  (against a purchase invoice)
-- ============================================================
CREATE TABLE IF NOT EXISTS payment_master (
    id                  BIGSERIAL PRIMARY KEY,

    party_id            BIGINT NOT NULL REFERENCES party_master(id)    ON DELETE RESTRICT,

    -- RECEIPT (customer pays us) | PAYMENT (we pay supplier)
    txn_type            VARCHAR(20) NOT NULL,

    -- Which document this settles
    reference_type      VARCHAR(20),        -- sale / purchase / advance / adjustment
    reference_id        BIGINT,             -- sales_master.id  OR  purchase_master.id

    txn_date            DATE           NOT NULL,
    amount              NUMERIC(12, 2) NOT NULL,

    payment_mode_id     BIGINT REFERENCES payment_mode_master(id) ON DELETE SET NULL,
    reference_no        VARCHAR(100),       -- cheque no / UTR / UPI ref
    notes               TEXT,

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payment_master_party_id       ON payment_master (party_id);
CREATE INDEX IF NOT EXISTS idx_payment_master_txn_type       ON payment_master (txn_type);
CREATE INDEX IF NOT EXISTS idx_payment_master_reference_type ON payment_master (reference_type);
CREATE INDEX IF NOT EXISTS idx_payment_master_reference_id   ON payment_master (reference_id);
CREATE INDEX IF NOT EXISTS idx_payment_master_txn_date       ON payment_master (txn_date);
CREATE INDEX IF NOT EXISTS idx_payment_master_mode_id        ON payment_master (payment_mode_id);

DROP TRIGGER IF EXISTS trg_payment_master_updated_at ON payment_master;
CREATE TRIGGER trg_payment_master_updated_at
    BEFORE UPDATE ON payment_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
