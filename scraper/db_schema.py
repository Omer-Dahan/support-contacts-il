#!/usr/bin/env python3
"""
Database Schema & FTS5 Initialization
Support Contacts IL Project
"""

import sqlite3
import os

DB_PATH = "/home/vm/projects/support-contacts-il/data/sherutplus.db"

def init_db(db_path=DB_PATH):
    """
    Initializes the SQLite database tables, indexes, FTS5 virtual table, and sync triggers.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        legal_name TEXT,
        company_reg_id TEXT,
        category TEXT,
        description TEXT,
        logo_url TEXT,
        website_url TEXT,
        social_links TEXT,
        brand_color TEXT,
        ai_summary TEXT,
        source_url TEXT NOT NULL,
        scraped_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS phones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        number TEXT NOT NULL,
        clean_number TEXT NOT NULL,
        label TEXT,
        purpose TEXT,
        is_primary INTEGER DEFAULT 0,
        kind TEXT DEFAULT 'phone',
        UNIQUE(company_id, clean_number, kind)
    );

    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        email TEXT NOT NULL,
        label TEXT,
        contact_type TEXT,
        UNIQUE(company_id, email)
    );

    CREATE TABLE IF NOT EXISTS whatsapp (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        phone TEXT,
        url TEXT NOT NULL,
        label TEXT,
        UNIQUE(company_id, url)
    );

    CREATE TABLE IF NOT EXISTS hours (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        days TEXT,
        opens TEXT,
        closes TEXT,
        raw_text TEXT
    );

    CREATE TABLE IF NOT EXISTS branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        name TEXT,
        city TEXT,
        address TEXT,
        phone TEXT,
        email TEXT,
        hours TEXT,
        latitude REAL,
        longitude REAL
    );

    CREATE TABLE IF NOT EXISTS metrics (
        company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        response_rate REAL,
        unanswered_rate REAL,
        avg_response_hours REAL,
        avg_emails_to_resolve REAL,
        calm_pct REAL,
        angry_pct REAL,
        raw_metrics TEXT
    );

    CREATE TABLE IF NOT EXISTS faqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        company_slug TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);
    CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
    CREATE INDEX IF NOT EXISTS idx_companies_slug ON companies(slug);
    CREATE INDEX IF NOT EXISTS idx_phones_company ON phones(company_id);
    CREATE INDEX IF NOT EXISTS idx_phones_number ON phones(clean_number);
    CREATE INDEX IF NOT EXISTS idx_emails_company ON emails(company_id);
    CREATE INDEX IF NOT EXISTS idx_branches_company ON branches(company_id);
    CREATE INDEX IF NOT EXISTS idx_branches_city ON branches(city);

    -- FTS5 Virtual Table for Full-Text Search
    CREATE VIRTUAL TABLE IF NOT EXISTS companies_fts USING fts5(
        company_id UNINDEXED,
        slug UNINDEXED,
        name,
        legal_name,
        category,
        description,
        ai_summary,
        cities,
        phone_labels,
        tokenize='unicode61 remove_diacritics 2'
    );
    """)

    # Create synchronization triggers
    cursor.executescript("""
    -- Companies INSERT trigger
    CREATE TRIGGER IF NOT EXISTS trg_companies_fts_ai AFTER INSERT ON companies BEGIN
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        VALUES (
            new.id,
            new.slug,
            new.name,
            COALESCE(new.legal_name, ''),
            COALESCE(new.category, ''),
            COALESCE(new.description, ''),
            COALESCE(new.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = new.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = new.id), '')
        );
    END;

    -- Companies UPDATE trigger
    CREATE TRIGGER IF NOT EXISTS trg_companies_fts_au AFTER UPDATE ON companies BEGIN
        DELETE FROM companies_fts WHERE company_id = old.id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        VALUES (
            new.id,
            new.slug,
            new.name,
            COALESCE(new.legal_name, ''),
            COALESCE(new.category, ''),
            COALESCE(new.description, ''),
            COALESCE(new.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = new.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = new.id), '')
        );
    END;

    -- Companies DELETE trigger
    CREATE TRIGGER IF NOT EXISTS trg_companies_fts_ad AFTER DELETE ON companies BEGIN
        DELETE FROM companies_fts WHERE company_id = old.id;
    END;

    -- Branches change triggers
    CREATE TRIGGER IF NOT EXISTS trg_branches_fts_ai AFTER INSERT ON branches BEGIN
        DELETE FROM companies_fts WHERE company_id = new.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = new.company_id;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_branches_fts_au AFTER UPDATE ON branches BEGIN
        DELETE FROM companies_fts WHERE company_id = new.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = new.company_id;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_branches_fts_ad AFTER DELETE ON branches BEGIN
        DELETE FROM companies_fts WHERE company_id = old.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = old.company_id;
    END;

    -- Phones change triggers
    CREATE TRIGGER IF NOT EXISTS trg_phones_fts_ai AFTER INSERT ON phones BEGIN
        DELETE FROM companies_fts WHERE company_id = new.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = new.company_id;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_phones_fts_au AFTER UPDATE ON phones BEGIN
        DELETE FROM companies_fts WHERE company_id = new.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = new.company_id;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_phones_fts_ad AFTER DELETE ON phones BEGIN
        DELETE FROM companies_fts WHERE company_id = old.company_id;
        INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
        SELECT 
            c.id, c.slug, c.name, COALESCE(c.legal_name, ''), COALESCE(c.category, ''), COALESCE(c.description, ''), COALESCE(c.ai_summary, ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
        FROM companies c WHERE c.id = old.company_id;
    END;
    """)
    conn.commit()
    conn.close()

def rebuild_fts(db_path=DB_PATH):
    """
    Rebuilds and populates the companies_fts virtual table from existing DB records.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS companies_fts USING fts5(company_id UNINDEXED, slug UNINDEXED, name, legal_name, category, description, ai_summary, cities, phone_labels, tokenize='unicode61 remove_diacritics 2');")
    cursor.execute("DELETE FROM companies_fts;")
    cursor.execute("""
    INSERT INTO companies_fts(company_id, slug, name, legal_name, category, description, ai_summary, cities, phone_labels)
    SELECT 
        c.id,
        c.slug,
        c.name,
        COALESCE(c.legal_name, ''),
        COALESCE(c.category, ''),
        COALESCE(c.description, ''),
        COALESCE(c.ai_summary, ''),
        COALESCE((SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != ''), ''),
        COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(label, '') || ' ' || COALESCE(purpose, '')) FROM phones WHERE company_id = c.id), '')
    FROM companies c;
    """)
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

if __name__ == "__main__":
    init_db(DB_PATH)
    count = rebuild_fts(DB_PATH)
    print(f"Database initialized and companies_fts populated with {count} records.")
