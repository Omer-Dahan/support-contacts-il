#!/usr/bin/env python3
"""
VCF (vCard) Export Utility
Support Contacts IL Project
Allows exporting filtered contacts from SQLite database to standard vCard (.vcf) file.
"""

import sys
import os
import sqlite3
import argparse
import json
import re

# Set up module path and default database path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..' if SCRIPT_DIR.endswith('scraper') else '.'))
DB_PATH = os.path.join(BASE_DIR, "data", "sherutplus.db")

def escape_vcard_text(text):
    if not text:
        return ""
    text = str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
    text = text.replace('\r\n', '\\n').replace('\n', '\\n')
    return text

def company_to_vcard(company, phones, emails, whatsapp, branches, hours, metrics):
    name = (company.get('name') or '').strip() or (company.get('legal_name') or '').strip() or (company.get('slug') or '').strip() or 'ללא שם'
    escaped_name = escape_vcard_text(name)
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN;CHARSET=UTF-8:{escaped_name}",
        f"ORG;CHARSET=UTF-8:{escaped_name}"
    ]

    if company.get('legal_name') and company.get('legal_name').strip() != name:
        lines.append(f"TITLE;CHARSET=UTF-8:{escape_vcard_text(company['legal_name'].strip())}")

    if company.get('category'):
        lines.append(f"CATEGORIES;CHARSET=UTF-8:{escape_vcard_text(company['category'].strip())}")

    # Phones
    for p in phones:
        num = (p.get('clean_number') or p.get('number') or '').strip()
        if not num:
            continue
        kind = p.get('kind', 'phone')
        label = p.get('label') or ''
        is_primary = p.get('is_primary')
        
        type_parts = ["WORK"]
        if kind == 'fax':
            type_parts.append("FAX")
        elif kind == 'sms':
            type_parts.append("CELL")
        else:
            type_parts.append("VOICE")
            
        if is_primary:
            type_parts.append("PREF")
            
        type_str = ",".join(type_parts)
        if label:
            lines.append(f"X-ABLabel;CHARSET=UTF-8:{escape_vcard_text(label)}")
        lines.append(f"TEL;TYPE={type_str}:{num}")

    # Emails
    for e in emails:
        em = (e.get('email') or '').strip()
        if em:
            lines.append(f"EMAIL;TYPE=INTERNET,WORK:{em}")

    # URLs
    if company.get('website_url'):
        lines.append(f"URL:{company['website_url']}")
    if company.get('source_url'):
        lines.append(f"URL;TYPE=SHERUTPLUS:{company['source_url']}")

    # Logo
    if company.get('logo_url'):
        lines.append(f"PHOTO;VALUE=URI:{company['logo_url']}")

    # Addresses / Branches
    for b in branches[:3]:
        street = escape_vcard_text(b.get('address') or '')
        city = escape_vcard_text(b.get('city') or '')
        lines.append(f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{street};{city};;IL;")

    # Notes
    notes = []
    if company.get('company_reg_id'):
        notes.append(f"ח.פ.: {company['company_reg_id']}")
    if company.get('description'):
        notes.append(company['description'])
    if company.get('ai_summary'):
        notes.append(f"סיכום שירות: {company['ai_summary']}")
    if whatsapp:
        wa_entries = []
        for w in whatsapp:
            wa_p = (w.get('phone') or '').strip()
            wa_u = (w.get('url') or '').strip()
            if wa_p and wa_u and wa_p != wa_u:
                wa_entries.append(f"{wa_p} ({wa_u})")
            elif wa_p or wa_u:
                wa_entries.append(wa_p or wa_u)
        if wa_entries:
            notes.append(f"WhatsApp: {', '.join(wa_entries)}")
    if hours:
        hour_strs = [h.get('raw_text') or f"{h.get('opens')}-{h.get('closes')}" for h in hours if h.get('raw_text') or h.get('opens')]
        if hour_strs:
            notes.append(f"שעות פעילות: {', '.join(hour_strs)}")
            
    if notes:
        full_note = "\n\n".join(notes)
        lines.append(f"NOTE;CHARSET=UTF-8:{escape_vcard_text(full_note)}")

    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"

def export_contacts(db_path=DB_PATH, category=None, slugs=None, query=None, all_companies=False, output_file=None, limit=None):
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if category:
        where_clauses.append("c.category = ?")
        params.append(category)

    if slugs:
        slug_list = [s.strip() for s in slugs.split(',') if s.strip()]
        placeholders = ",".join("?" for _ in slug_list)
        where_clauses.append(f"c.slug IN ({placeholders})")
        params.extend(slug_list)

    if query:
        where_clauses.append("(c.name LIKE ? OR c.description LIKE ? OR c.slug LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    if not where_clauses and not all_companies:
        print("Please specify a filter (--category, --slugs, --query) or use --all to export all contacts.")
        conn.close()
        return False

    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    limit_sql = f" LIMIT {int(limit)}" if limit else ""

    query_sql = f"""
    SELECT c.* FROM companies c
    {where_sql}
    ORDER BY c.name
    {limit_sql}
    """

    cursor.execute(query_sql, params)
    companies = cursor.fetchall()

    if not companies:
        print("No companies matched the given criteria.")
        conn.close()
        return False

    print(f"Found {len(companies)} matching companies. Generating vCards...")

    vcards = []
    for comp_row in companies:
        comp = dict(comp_row)
        cid = comp['id']

        cursor.execute("SELECT * FROM phones WHERE company_id = ? ORDER BY is_primary DESC, id ASC", (cid,))
        phones = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM emails WHERE company_id = ? ORDER BY id ASC", (cid,))
        emails = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM whatsapp WHERE company_id = ? ORDER BY id ASC", (cid,))
        whatsapp = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM branches WHERE company_id = ? ORDER BY id ASC", (cid,))
        branches = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM hours WHERE company_id = ? ORDER BY id ASC", (cid,))
        hours = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM metrics WHERE company_id = ?", (cid,))
        m_row = cursor.fetchone()
        metrics = dict(m_row) if m_row else {}

        vcard_text = company_to_vcard(comp, phones, emails, whatsapp, branches, hours, metrics)
        vcards.append(vcard_text)

    conn.close()

    if not output_file:
        safe_name = re.sub(r'[^a-zA-Z0-9_\u0590-\u05FF]', '_', category or (slugs or 'support_contacts'))
        output_file = os.path.join(BASE_DIR, "data", f"{safe_name}.vcf")

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("".join(vcards))

    print(f"Exported {len(vcards)} contacts successfully to: {output_file}")
    return True

def list_categories(db_path=DB_PATH):
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COALESCE(category, 'ללא קטגוריה') as cat, COUNT(*) as count 
    FROM companies 
    GROUP BY cat 
    ORDER BY count DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    print("\n--- Available Categories ---")
    for cat, count in rows:
        print(f"  • {cat}: {count} חברות")
    print("-----------------------------\n")

def main():
    parser = argparse.ArgumentParser(description="Export Support Contacts IL to VCF format")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database")
    parser.add_argument("--category", "-c", help="Filter by exact category name (e.g. 'אינטרנט')")
    parser.add_argument("--slugs", "-s", help="Filter by comma-separated company slugs (e.g. 'bezeq,hot,partner')")
    parser.add_argument("--query", "-q", help="Search by keyword in name, description, or slug")
    parser.add_argument("--all", "-a", action="store_true", help="Export all companies")
    parser.add_argument("--output", "-o", help="Output VCF file path")
    parser.add_argument("--limit", "-l", type=int, help="Limit number of exported companies")
    parser.add_argument("--list-categories", action="store_true", help="List all available categories in the DB")

    args = parser.parse_args()

    if args.list_categories:
        list_categories(args.db)
    else:
        export_contacts(
            db_path=args.db,
            category=args.category,
            slugs=args.slugs,
            query=args.query,
            all_companies=args.all,
            output_file=args.output,
            limit=args.limit
        )

if __name__ == "__main__":
    main()
