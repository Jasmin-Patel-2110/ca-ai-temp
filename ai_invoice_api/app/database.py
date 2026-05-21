import pymysql
import pymysql.cursors
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


def get_connection():
    """Open and return a new PyMySQL connection to XAMPP MySQL."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def init_db():
    """Create the database and users table if they do not exist,
    then add any new columns that were introduced after initial creation."""
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(f"USE `{DB_NAME}`")

            # ── Users table ───────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id              INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    name            VARCHAR(120) NOT NULL,
                    company_name    VARCHAR(200) NOT NULL,
                    email           VARCHAR(200) NOT NULL UNIQUE,
                    hashed_password VARCHAR(255) NOT NULL,
                    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            for col_sql in [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gst_number   VARCHAR(20)  DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS address       TEXT         DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_number VARCHAR(15)  DEFAULT NULL",
            ]:
                cur.execute(col_sql)

            # ── Invoices new columns (safe to run every startup) ───────────────
            cur.execute(
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "
                "product_name VARCHAR(500) DEFAULT NULL AFTER client_name"
            )
            cur.execute(
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "
                "invoice_number VARCHAR(100) DEFAULT NULL AFTER doc_id"
            )
            # label_type: 'accounting' (default) or 'business'
            cur.execute(
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "
                "label_type VARCHAR(20) NOT NULL DEFAULT 'accounting' AFTER client_name"
            )
            # is_line_item_split:
            #   1 = row created as part of a multi-product line-item split → S3 kept on delete
            #   0 = normal single-product invoice → S3 deleted on delete
            cur.execute(
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "
                "is_line_item_split TINYINT(1) NOT NULL DEFAULT 0"
            )

            # Buyer/Seller explicit columns
            for col_sql in [
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS buyer_party_name      VARCHAR(255) DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS seller_party_name     VARCHAR(255) DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS buyer_contact_number  VARCHAR(50)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS seller_contact_number VARCHAR(50)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS buyer_pan_number       VARCHAR(50)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS seller_pan_number      VARCHAR(50)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS buyer_gst_number      VARCHAR(20)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS seller_gst_number     VARCHAR(20)  DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS buyer_location         LONGTEXT     DEFAULT NULL",
                "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS seller_location        LONGTEXT     DEFAULT NULL",
            ]:
                cur.execute(col_sql)

            # Drop legacy columns
            for legacy_col in ("pan_number", "contact_number", "location", "gst_number"):
                try:
                    cur.execute(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'invoices' AND COLUMN_NAME = %s",
                        (DB_NAME, legacy_col),
                    )
                    if cur.fetchone():
                        cur.execute(f"ALTER TABLE invoices DROP COLUMN {legacy_col}")
                except Exception:
                    pass

            # Drop unique constraint on doc_id to allow multi-page PDF grouping
            try:
                cur.execute("ALTER TABLE invoices DROP INDEX doc_id")
            except Exception:
                pass

            # ── Token blacklist ───────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    id         INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    token      TEXT     NOT NULL,
                    expired_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ── Invoices table (full definition for fresh DBs) ────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id                 INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    user_id            VARCHAR(50)   NOT NULL,
                    doc_id             VARCHAR(50)   NOT NULL,
                    invoice_number     VARCHAR(100)  DEFAULT NULL,
                    client_name        VARCHAR(255),
                    label_type         VARCHAR(20)   NOT NULL DEFAULT 'accounting',
                    industry           VARCHAR(255),
                    category           VARCHAR(255),
                    sub_category       VARCHAR(255),
                    transaction_type   VARCHAR(100),
                    status             VARCHAR(50)   DEFAULT 'pending_extraction',
                    invoice_date       DATE,
                    gst                VARCHAR(50),
                    cgst               VARCHAR(50),
                    sgst               VARCHAR(50),
                    igst               VARCHAR(50),
                    total              VARCHAR(50),
                    quantity           VARCHAR(50),
                    rate               VARCHAR(50),
                    amount             DOUBLE,
                    amount_paid        DOUBLE,
                    balance_amount     DOUBLE,
                    payment_mode       VARCHAR(100),
                    additional_detail  LONGTEXT,
                    is_line_item_split TINYINT(1)    NOT NULL DEFAULT 0,
                    created_datetime   DATETIME      DEFAULT CURRENT_TIMESTAMP,
                    updated_datetime   DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ── Documents table ───────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id         INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    doc_id     VARCHAR(50)   NOT NULL,
                    doc_name   VARCHAR(255)  NOT NULL,
                    s3_key     VARCHAR(500)  NOT NULL,
                    s3_url     VARCHAR(1000) NOT NULL,
                    created_at DATETIME      DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_doc_id (doc_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # Migrate old schema (invoice_id) to new (doc_id)
            try:
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'invoice_id'",
                    (DB_NAME,)
                )
                if cur.fetchone():
                    cur.execute("ALTER TABLE documents ADD COLUMN doc_id VARCHAR(50) DEFAULT NULL")
                    cur.execute("""
                        UPDATE documents d
                        JOIN invoices i ON d.invoice_id = i.id
                        SET d.doc_id = i.doc_id
                    """)
                    cur.execute("""
                        DELETE d1 FROM documents d1
                        JOIN documents d2 ON d1.doc_id = d2.doc_id AND d1.id > d2.id
                    """)
                    cur.execute("ALTER TABLE documents MODIFY doc_id VARCHAR(50) NOT NULL")
                    try:
                        cur.execute("ALTER TABLE documents DROP FOREIGN KEY documents_ibfk_1")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE documents DROP COLUMN invoice_id")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE documents ADD UNIQUE KEY uk_doc_id (doc_id)")
                    except Exception:
                        pass
            except Exception:
                pass

            # Migrate subcategory -> sub_category
            try:
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'invoices' AND COLUMN_NAME = 'subcategory'",
                    (DB_NAME,)
                )
                if cur.fetchone():
                    cur.execute("ALTER TABLE invoices CHANGE COLUMN subcategory sub_category VARCHAR(255)")
            except Exception:
                pass

            # Migrate invoice_datetime -> invoice_date
            try:
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'invoices' AND COLUMN_NAME = 'invoice_datetime'",
                    (DB_NAME,)
                )
                if cur.fetchone():
                    cur.execute("ALTER TABLE invoices CHANGE COLUMN invoice_datetime invoice_date DATE")
            except Exception:
                pass

            # Migrate invoice_dateonly -> invoice_date
            try:
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'invoices' AND COLUMN_NAME = 'invoice_dateonly'",
                    (DB_NAME,)
                )
                if cur.fetchone():
                    cur.execute("ALTER TABLE invoices CHANGE COLUMN invoice_dateonly invoice_date DATE")
            except Exception:
                pass

            # Migrate s3_key/s3_url from invoices to documents
            try:
                cur.execute("""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'invoices' AND COLUMN_NAME = 's3_key'
                """, (DB_NAME,))
                if cur.fetchone():
                    cur.execute("""
                        INSERT IGNORE INTO documents (doc_id, doc_name, s3_key, s3_url)
                        SELECT doc_id, COALESCE(NULLIF(SUBSTRING_INDEX(s3_key, '/', -1), ''), 'doc'),
                               MIN(s3_key), MIN(s3_url)
                        FROM invoices
                        WHERE s3_key IS NOT NULL AND s3_key != ''
                        GROUP BY doc_id
                    """)
                cur.execute("ALTER TABLE invoices DROP COLUMN s3_key")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE invoices DROP COLUMN s3_url")
            except Exception:
                pass

            # Clean up data before enforcing ENUMs
            cur.execute("""
                UPDATE invoices
                SET status = 'pending_verification'
                WHERE status NOT IN ('pending_extraction', 'pending_verification', 'verified', 'error')
                   OR status IS NULL
            """)
            cur.execute("""
                UPDATE invoices
                SET transaction_type = 'Other'
                WHERE transaction_type NOT IN ('Sales', 'Expense', 'Purchase', 'Other')
                   AND transaction_type IS NOT NULL
            """)
            cur.execute("UPDATE invoices SET industry = NULL WHERE industry = 'Jwellers'")
            _INDUSTRY_VALID = (
                "Textile Manufacturing", "Textile Jobwork", "Supari", "Labour",
                "Jewellers", "IT", "Gov", "Hospital", "Diamond"
            )
            placeholders = ", ".join("%s" for _ in _INDUSTRY_VALID)
            cur.execute(
                f"UPDATE invoices SET industry = NULL WHERE industry IS NOT NULL "
                f"AND TRIM(industry) NOT IN ({placeholders})",
                _INDUSTRY_VALID,
            )

            # Enforce ENUMs
            cur.execute("""
                ALTER TABLE invoices
                MODIFY COLUMN transaction_type ENUM('Sales', 'Expense', 'Purchase', 'Other') DEFAULT NULL,
                MODIFY COLUMN status ENUM('pending_extraction', 'pending_verification', 'verified', 'error') DEFAULT 'pending_extraction'
            """)
            cur.execute("""
                ALTER TABLE invoices
                MODIFY COLUMN industry ENUM(
                    'Textile Manufacturing', 'Textile Jobwork', 'Supari', 'Labour',
                    'Jewellers', 'IT', 'Gov', 'Hospital', 'Diamond'
                ) DEFAULT NULL
            """)

            # ── Classifier metadata ───────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS classifier_meta (
                    id              INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    trained_samples INT      NOT NULL DEFAULT 0,
                    reset_count     INT      NOT NULL DEFAULT 0,
                    last_trained_at DATETIME DEFAULT NULL,
                    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("INSERT IGNORE INTO classifier_meta (id) VALUES (1)")

        conn.commit()
    finally:
        conn.close()