#!/usr/bin/env python3
"""
Full-Text Search (FTS5) Engine for SherutPlus / Support Contacts IL
Supports Hebrew tokenization, prefix matching, multi-word queries, and BM25 relevance ranking.
Can be run from CLI or imported as a module for Telegram bots and APIs.
"""

import sys
import os
import sqlite3
import argparse
import json
import re
from typing import List, Dict, Any, Optional

# Set up module path and default database path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
SCRAPER_DIR = os.path.join(SCRIPT_DIR, 'scraper') if not SCRIPT_DIR.endswith('scraper') else SCRIPT_DIR
if SCRAPER_DIR not in sys.path:
    sys.path.insert(0, SCRAPER_DIR)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..' if os.path.dirname(os.path.abspath(__file__)).endswith('scraper') else '.'))
DB_PATH = os.path.join(BASE_DIR, "data", "sherutplus.db")

def clean_hebrew_text(text: str) -> str:
    """Strips Hebrew niqqud, cantillation marks, and zero-width characters."""
    if not text:
        return ""
    # Remove Hebrew vowels/niqqud and cantillation marks (U+0591 to U+05C7)
    # Also remove zero-width chars (U+200B-U+200F, U+FEFF)
    text = re.sub(r'[\u0591-\u05C7\u200B-\u200F\uFEFF]', '', text)
    return text.strip()

def build_fts_query(user_query: str) -> str:
    """
    Builds a robust FTS5 query string from free-text user input.
    Handles Hebrew prefixes (e.g. ה), wildcards (*), and multi-word phrases.
    """
    clean_q = clean_hebrew_text(user_query)
    # Remove characters that have special meaning in FTS5 syntax
    sanitized = re.sub(r'[\"\'*^:()\[\]{}+~-]', ' ', clean_q)
    tokens = [t.strip() for t in sanitized.split() if t.strip()]
    
    if not tokens:
        return ""

    def get_variants(token: str) -> List[str]:
        variants = [token]
        # Hebrew definite article 'ה'
        if token.startswith('ה') and len(token) > 2:
            variants.append(token[1:])
        elif not token.startswith('ה') and len(token) >= 2:
            variants.append('ה' + token)
        # Wildcard suffix for plurals/inflections
        variants.append(f"{token}*")
        return list(dict.fromkeys(variants))

    if len(tokens) == 1:
        return " OR ".join(get_variants(tokens[0]))

    # For multi-word queries: full phrase boost + individual token variants
    exact_phrase = '"' + " ".join(tokens) + '"'
    parts = [exact_phrase]
    for tok in tokens:
        vars_list = get_variants(tok)
        parts.append("(" + " OR ".join(vars_list) + ")")

    return " OR ".join(parts)

def ensure_fts_ready(conn: sqlite3.Connection):
    """Ensures companies_fts exists and has records."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies_fts'")
    if not cursor.fetchone():
        try:
            from db_schema import init_db, rebuild_fts
            init_db(DB_PATH)
            rebuild_fts(DB_PATH)
        except ImportError:
            pass
    else:
        cursor.execute("SELECT COUNT(*) FROM companies_fts")
        if cursor.fetchone()[0] == 0:
            try:
                from db_schema import rebuild_fts
                rebuild_fts(DB_PATH)
            except ImportError:
                pass

def search_companies(
    query: str,
    category: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 10,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """
    Executes a free-text search using FTS5 and BM25 ranking,
    with fallbacks for direct phone, email, slug, and reg-id lookups.
    Returns a list of matching company dictionaries.
    """
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_fts_ready(conn)
    cursor = conn.cursor()

    query_str = (query or "").strip()
    fts_match_expr = build_fts_query(query_str) if query_str else ""

    params = []
    where_conditions = []

    if fts_match_expr:
        where_conditions.append("fts.companies_fts MATCH ?")
        params.append(fts_match_expr)

    if category:
        where_conditions.append("c.category = ?")
        params.append(category)

    if city:
        where_conditions.append("EXISTS (SELECT 1 FROM branches b WHERE b.company_id = c.id AND (b.city LIKE ? OR b.address LIKE ?))")
        params.extend([f"%{city}%", f"%{city}%"])

    where_clause = ("WHERE " + " AND ".join(where_conditions)) if where_conditions else ""

    # FTS BM25 column weights: name=10.0, legal_name=5.0, category=5.0, description=2.0, ai_summary=2.0, cities=6.0, phone_labels=3.0
    if fts_match_expr:
        sql = f"""
        SELECT 
            c.id,
            c.slug,
            COALESCE(NULLIF(TRIM(c.name), ''), NULLIF(TRIM(c.legal_name), ''), c.slug, 'ללא שם') as name,
            c.legal_name,
            c.company_reg_id,
            c.category,
            c.description,
            c.ai_summary,
            c.website_url,
            c.logo_url,
            c.source_url,
            (SELECT COALESCE(NULLIF(clean_number, ''), number) FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone,
            (SELECT label FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone_label,
            (SELECT email FROM emails WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_email,
            (SELECT COALESCE(NULLIF(phone, ''), url) FROM whatsapp WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_whatsapp,
            (SELECT COUNT(*) FROM branches WHERE company_id = c.id) as branch_count,
            (SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != '') as cities,
            bm25(companies_fts, 10.0, 5.0, 5.0, 2.0, 2.0, 6.0, 3.0) as rank
        FROM companies_fts fts
        JOIN companies c ON fts.company_id = c.id
        {where_clause}
        ORDER BY rank ASC
        LIMIT ?
        """
        params.append(int(limit))
    else:
        # If no text query, list by name or category
        sql = f"""
        SELECT 
            c.id,
            c.slug,
            COALESCE(NULLIF(TRIM(c.name), ''), NULLIF(TRIM(c.legal_name), ''), c.slug, 'ללא שם') as name,
            c.legal_name,
            c.company_reg_id,
            c.category,
            c.description,
            c.ai_summary,
            c.website_url,
            c.logo_url,
            c.source_url,
            (SELECT COALESCE(NULLIF(clean_number, ''), number) FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone,
            (SELECT label FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone_label,
            (SELECT email FROM emails WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_email,
            (SELECT COALESCE(NULLIF(phone, ''), url) FROM whatsapp WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_whatsapp,
            (SELECT COUNT(*) FROM branches WHERE company_id = c.id) as branch_count,
            (SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != '') as cities,
            0.0 as rank
        FROM companies c
        {where_clause}
        ORDER BY c.name ASC
        LIMIT ?
        """
        params.append(int(limit))

    rows = []
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []

    # If no results from FTS and a query string was provided, try targeted lookups (phone, email, slug, reg_id, substring)
    if not rows and query_str:
        digits_only = re.sub(r'\D', '', query_str)
        fb_conditions = []
        fb_params = []

        if len(digits_only) >= 3 or (query_str.startswith('*') and len(query_str) >= 3):
            fb_conditions.append("""EXISTS (
                SELECT 1 FROM phones p WHERE p.company_id = c.id AND (
                    p.clean_number LIKE ? OR p.number LIKE ?
                )
            ) OR EXISTS (
                SELECT 1 FROM whatsapp w WHERE w.company_id = c.id AND (
                    w.phone LIKE ? OR w.url LIKE ?
                )
            )""")
            fb_params.extend([f"%{digits_only}%", f"%{query_str}%", f"%{digits_only}%", f"%{digits_only}%"])

        if '@' in query_str:
            fb_conditions.append("EXISTS (SELECT 1 FROM emails e WHERE e.company_id = c.id AND e.email LIKE ?)")
            fb_params.append(f"%{query_str}%")

        if not fb_conditions:
            fb_conditions.append("c.name LIKE ? OR c.description LIKE ? OR c.legal_name LIKE ? OR c.slug LIKE ?")
            fb_params.extend([f"%{query_str}%", f"%{query_str}%", f"%{query_str}%", f"%{query_str}%"])

        if category:
            fb_conditions.append("c.category = ?")
            fb_params.append(category)

        if city:
            fb_conditions.append("EXISTS (SELECT 1 FROM branches b WHERE b.company_id = c.id AND (b.city LIKE ? OR b.address LIKE ?))")
            fb_params.extend([f"%{city}%", f"%{city}%"])

        fb_where = "WHERE " + " AND ".join(fb_conditions)
        fallback_sql = f"""
        SELECT 
            c.id, c.slug,
            COALESCE(NULLIF(TRIM(c.name), ''), NULLIF(TRIM(c.legal_name), ''), c.slug, 'ללא שם') as name,
            c.legal_name, c.company_reg_id, c.category, c.description, c.ai_summary,
            c.website_url, c.logo_url, c.source_url,
            (SELECT COALESCE(NULLIF(clean_number, ''), number) FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone,
            (SELECT label FROM phones WHERE company_id = c.id ORDER BY is_primary DESC, kind='phone' DESC, id ASC LIMIT 1) as primary_phone_label,
            (SELECT email FROM emails WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_email,
            (SELECT COALESCE(NULLIF(phone, ''), url) FROM whatsapp WHERE company_id = c.id ORDER BY id ASC LIMIT 1) as primary_whatsapp,
            (SELECT COUNT(*) FROM branches WHERE company_id = c.id) as branch_count,
            (SELECT GROUP_CONCAT(DISTINCT city) FROM branches WHERE company_id = c.id AND city IS NOT NULL AND city != '') as cities,
            1.0 as rank
        FROM companies c
        {fb_where}
        LIMIT ?
        """
        fb_params.append(int(limit))
        try:
            cursor.execute(fallback_sql, fb_params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            rows = []

    results = []
    for r in rows:
        item = dict(r)
        # Normalize rank score: positive number where higher is better
        item['relevance_score'] = round(abs(item['rank']), 2) if item['rank'] != 0.0 else 0.0
        # Parse cities into a clean list
        cities_str = item.get('cities') or ''
        city_list = [c.strip() for c in cities_str.split(',') if c.strip()]
        item['cities_list'] = city_list
        results.append(item)

    conn.close()
    return results

def get_company_details(company_id_or_slug, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetches full dossier for a specific company (phones, emails, whatsapp, branches, hours, faqs)."""
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if isinstance(company_id_or_slug, int) or (isinstance(company_id_or_slug, str) and company_id_or_slug.isdigit()):
        cursor.execute("SELECT * FROM companies WHERE id = ?", (int(company_id_or_slug),))
    else:
        cursor.execute("SELECT * FROM companies WHERE slug = ?", (str(company_id_or_slug),))

    comp_row = cursor.fetchone()
    if not comp_row:
        conn.close()
        return None

    company = dict(comp_row)
    cid = company['id']

    cursor.execute("SELECT * FROM phones WHERE company_id = ? ORDER BY is_primary DESC, id ASC", (cid,))
    company['phones'] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM emails WHERE company_id = ?", (cid,))
    company['emails'] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM whatsapp WHERE company_id = ? ORDER BY id ASC", (cid,))
    company['whatsapp'] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM hours WHERE company_id = ?", (cid,))
    company['hours'] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM branches WHERE company_id = ?", (cid,))
    company['branches'] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM metrics WHERE company_id = ?", (cid,))
    m_row = cursor.fetchone()
    company['metrics'] = dict(m_row) if m_row else None

    cursor.execute("SELECT question, answer FROM faqs WHERE company_id = ?", (cid,))
    company['faqs'] = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return company

def format_telegram_message(comp: Dict[str, Any]) -> str:
    """Helper to format a company result as a Telegram markdown message."""
    name = (comp.get('name') or '').strip() or (comp.get('legal_name') or '').strip() or (comp.get('slug') or '').strip() or 'ללא שם'
    lines = [f"🏢 *{name}*"]
    if comp.get('category'):
        lines.append(f"📁 *קטגוריה:* {comp['category']}")
    if comp.get('primary_phone'):
        label = f" ({comp['primary_phone_label']})" if comp.get('primary_phone_label') else ""
        lines.append(f"📞 *טלפון ראשי:* `{comp['primary_phone']}`{label}")
    if comp.get('primary_whatsapp'):
        lines.append(f"💬 *WhatsApp:* `{comp['primary_whatsapp']}`")
    if comp.get('primary_email'):
        lines.append(f"✉️ *אימייל:* `{comp['primary_email']}`")
    if comp.get('website_url'):
        lines.append(f"🌐 *אתר:* {comp['website_url']}")
    if comp.get('cities_list'):
        cities = ", ".join(comp['cities_list'][:4])
        more = f" ועוד ({len(comp['cities_list'])} ערים)" if len(comp['cities_list']) > 4 else ""
        lines.append(f"📍 *סניפים:* {cities}{more}")
    return "\n".join(lines)

def print_text_results(query: str, results: List[Dict[str, Any]], show_details: bool = False, db_path: str = DB_PATH):
    """Pretty prints search results to console."""
    if not results:
        print(f"\nלא נמצאו תוצאות עבור החיפוש: \"{query}\"")
        return

    print("\n" + "=" * 80)
    print(f"תוצאות חיפוש עבור: \"{query}\" (נמצאו {len(results)} תוצאות)")
    print("=" * 80)

    for idx, item in enumerate(results, start=1):
        name = (item.get('name') or '').strip() or (item.get('legal_name') or '').strip() or (item.get('slug') or '').strip() or 'ללא שם'
        cat = (item.get('category') or '').strip() or 'כללי'
        phone = (item.get('primary_phone') or '').strip() or 'אין מספר ראשי'
        phone_label = f" ({item['primary_phone_label']})" if item.get('primary_phone_label') else ""
        score = item.get('relevance_score', 0.0)
        
        cities = item.get('cities_list') or []
        branch_count = item.get('branch_count', 0)
        if cities:
            cities_snippet = ", ".join(cities[:4])
            if len(cities) > 4:
                cities_snippet += f" ועוד (סה\"כ {branch_count} סניפים ב-{len(cities)} ערים)"
        elif branch_count > 0:
            cities_snippet = f"{branch_count} סניפים"
        else:
            cities_snippet = "אין סניפים פיזיים"

        print(f"\n{idx}. {name} | קטגוריה: {cat} | ציון רלוונטיות: {score}")
        print(f"   • טלפון ראשי: {phone}{phone_label}")
        print(f"   • פריסת סניפים/ערים: {cities_snippet}")
        
        if item.get('primary_whatsapp'):
            print(f"   • WhatsApp: {item['primary_whatsapp']}")
        if item.get('primary_email'):
            print(f"   • אימייל: {item['primary_email']}")
        if item.get('website_url'):
            print(f"   • אתר: {item['website_url']}")

        if show_details:
            details = get_company_details(item['id'], db_path=db_path)
            if details:
                if details.get('phones') and len(details['phones']) > 1:
                    extra_phones = [
                        f"{(p.get('clean_number') or p.get('number') or '').strip()} ({p.get('label') or p.get('kind')})"
                        for p in details['phones'][1:]
                        if (p.get('clean_number') or p.get('number'))
                    ]
                    if extra_phones:
                        print(f"   • טלפונים נוספים: {', '.join(extra_phones)}")
                if details.get('whatsapp') and len(details['whatsapp']) > 1:
                    extra_wa = [
                        f"{(w.get('phone') or w.get('url') or '').strip()} ({w.get('label') or 'WhatsApp'})"
                        for w in details['whatsapp'][1:]
                        if (w.get('phone') or w.get('url'))
                    ]
                    if extra_wa:
                        print(f"   • WhatsApp נוסף: {', '.join(extra_wa)}")
                if details.get('description'):
                    desc_snippet = details['description'][:160].replace('\n', ' ')
                    print(f"   • תיאור: {desc_snippet}...")
                if details.get('ai_summary'):
                    sum_snippet = details['ai_summary'][:140].replace('\n', ' ')
                    print(f"   • סיכום AI: {sum_snippet}...")
                if details.get('hours'):
                    h_strs = [h.get('raw_text') or f"{h.get('days')}: {h.get('opens')}-{h.get('closes')}" for h in details['hours']]
                    print(f"   • שעות פעילות: {', '.join(h_strs[:2])}")
    print("\n" + "=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Free-text search (FTS5) for Support Contacts IL database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות לשימוש:
  python scraper/search.py "חשמל"
  python scraper/search.py "תל אביב"
  python scraper/search.py "בנק מזרחי"
  python scraper/search.py "ביטוח רכב" --category "ביטוח"
  python scraper/search.py "אינטרנט" --json
  python scraper/search.py --rebuild-fts
"""
    )
    parser.add_argument("query", nargs="?", default="", help="טקסט חופשי לחיפוש (שם חברה, קטגוריה, עיר, שירות וכו')")
    parser.add_argument("--category", "-c", help="סינון לפי קטגוריה")
    parser.add_argument("--city", help="סינון לפי עיר סניף")
    parser.add_argument("--limit", "-l", type=int, default=10, help="כמות תוצאות מקסימלית (ברירת מחדל 10)")
    parser.add_argument("--details", "-v", action="store_true", help="הצגת פרטים מורחבים (כל הטלפונים, תיאור, שעות)")
    parser.add_argument("--json", "-j", action="store_true", help="הדפסת תוצאות בפורמט JSON")
    parser.add_argument("--db", default=DB_PATH, help="נתיב למסד הנתונים SQLite")
    parser.add_argument("--rebuild-fts", action="store_true", help="בנייה מחדש של אינדקס ה-FTS5")

    args = parser.parse_args()

    if args.rebuild_fts:
        try:
            from db_schema import rebuild_fts
            c = rebuild_fts(args.db)
            print(f"FTS5 index rebuilt successfully with {c} records.")
        except Exception as e:
            print(f"Error rebuilding FTS5 index: {e}", file=sys.stderr)
        return

    if not args.query and not args.category and not args.city:
        parser.print_help()
        sys.exit(0)

    results = search_companies(
        query=args.query,
        category=args.category,
        city=args.city,
        limit=args.limit,
        db_path=args.db
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_text_results(args.query or f"סינון: קטגוריה={args.category}, עיר={args.city}", results, show_details=args.details, db_path=args.db)

if __name__ == "__main__":
    main()
