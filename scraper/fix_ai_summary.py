#!/usr/bin/env python3
"""
Fix Broken ai_summary in SherutPlus Database and Raw JSONL
Extracts SVG/role=img sentiment data (aria-label) and inquiries count.
Support Contacts IL Project
"""

import sys
import os
import time
import json
import re
import html as html_lib
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, "data", "sherutplus.db")
JSONL_PATH = os.path.join(BASE_DIR, "data", "sherutplus_raw.jsonl")

if os.path.join(BASE_DIR, 'scraper') not in sys.path:
    sys.path.insert(0, os.path.join(BASE_DIR, 'scraper'))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
}


def extract_ai_summary(raw_html: str) -> str | None:
    """
    Extracts sentiment analysis from SVG/role=img aria-label and inquiries count.
    Returns clean Hebrew formatted string, e.g.:
    "📊 ניתוח פניות (282 פניות גולשים): רגוע 30%, מתוסכל 56%, כועס 13%"
    or None if no sentiment data exists.
    """
    if not raw_html:
        return None

    text = html_lib.unescape(raw_html)

    # 1. Look for aria-label with "פילוח רגשות"
    m_sentiment = re.search(r'aria-label=[\"\']\s*(פילוח רגשות:[^\"\']+)[\"\']', text)
    if not m_sentiment:
        # Fallback: any role="img" with sentiment keywords
        m_sentiment = re.search(r'role=[\"\']img[\"\'][^>]*aria-label=[\"\']([^\"\']*(?:מתוסכל|כועס|רגוע|מרוצה|מיואש|מאוכזב)[^\"\']*)[\"\']', text)
        if not m_sentiment:
            m_sentiment = re.search(r'aria-label=[\"\']([^\"\']*(?:מתוסכל|כועס|רגוע|מרוצה|מיואש|מאוכזב)\s*\d+%[^\"\']*)[\"\']', text)

    if not m_sentiment:
        return None

    sentiment_raw = m_sentiment.group(1).strip()
    sentiment_clean = re.sub(r'^פילוח רגשות:\s*', '', sentiment_raw).strip()
    # Normalize internal whitespaces
    sentiment_clean = re.sub(r'\s+', ' ', sentiment_clean)

    # 2. Extract inquiries count if present
    inq_m = re.search(r'מבוסס על\s*(?:<[^>]+>)?\s*([0-9,]+)\s*(?:<[^>]+>)?\s*פניות גולשים', text)
    if not inq_m:
        inq_m = re.search(r'מבוסס על\s*([0-9,]+)\s*פניות גולשים', text)

    if inq_m:
        inq_cnt = inq_m.group(1).replace(',', '').strip()
        return f"📊 ניתוח פניות ({inq_cnt} פניות גולשים): {sentiment_clean}"
    else:
        return f"📊 ניתוח פניות: {sentiment_clean}"


def is_broken_summary(summary: str | None) -> bool:
    """Checks if ai_summary is a broken fragment without data."""
    if not summary:
        return False  # None/empty is treated as no summary, not broken fragment
    cleaned = summary.strip()
    if "פילוח רגשות" in cleaned and "%" not in cleaned:
        return True
    if "מבוסס על" in cleaned and "פילוח" in cleaned and "%" not in cleaned:
        return True
    if cleaned.startswith("📊") and "%" not in cleaned and len(cleaned) < 300:
        return True
    if cleaned.endswith("פילוח רגשות של לקוחות על פי סוג פנייה:"):
        return True
    return False


def fix_all_summaries(max_workers=4, db_path=DB_PATH, jsonl_path=JSONL_PATH):
    print("=" * 60)
    print("SherutPlus AI Summary Repair Tool")
    print(f"Database: {db_path}")
    print(f"JSONL: {jsonl_path}")
    print(f"Workers: {max_workers}")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, slug, name, source_url, ai_summary FROM companies ORDER BY id")
    companies = cursor.fetchall()
    total_companies = len(companies)

    broken_initial = [c for c in companies if is_broken_summary(c[4])]
    print(f"Total companies in DB: {total_companies}")
    print(f"Broken ai_summary records detected: {len(broken_initial)}")

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=max_workers * 2, pool_maxsize=max_workers * 2, max_retries=2)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)

    def fetch_and_parse(comp):
        cid, slug, name, url, old_summary = comp
        target_url = url or f"https://sherutplus.com/{slug}"
        try:
            r = session.get(target_url, timeout=20)
            if r.status_code == 200:
                new_summary = extract_ai_summary(r.text)
                return cid, slug, name, target_url, new_summary, None
            else:
                return cid, slug, name, target_url, None, f"HTTP {r.status_code}"
        except Exception as e:
            return cid, slug, name, target_url, None, str(e)

    print(f"\nFetching pages and extracting sentiment data...")
    start_time = time.time()

    updated_map = {}  # slug -> new_summary
    db_updates = []   # (new_summary, now_str, cid)
    fixed_with_data = 0
    set_to_null = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_comp = {executor.submit(fetch_and_parse, c): c for c in companies}
        done_count = 0

        for future in as_completed(future_to_comp):
            done_count += 1
            cid, slug, name, url, new_summary, err = future.result()

            if err:
                errors += 1
                print(f"[{done_count}/{total_companies}] ERROR for {slug}: {err}")
            else:
                updated_map[slug] = new_summary
                now_str = datetime.now().isoformat()
                db_updates.append((new_summary, now_str, cid))

                if new_summary:
                    fixed_with_data += 1
                else:
                    set_to_null += 1

            if done_count % 50 == 0 or done_count == total_companies:
                elapsed = time.time() - start_time
                rate = done_count / elapsed if elapsed > 0 else 0
                print(f"[{done_count}/{total_companies}] ({(done_count/total_companies)*100:.1f}%) | "
                      f"With Data: {fixed_with_data} | Null: {set_to_null} | Err: {errors} | {rate:.1f} req/s")

    # 1. Update SQLite DB
    print("\nUpdating SQLite database...")
    cursor.executemany("UPDATE companies SET ai_summary = ?, updated_at = ? WHERE id = ?", db_updates)
    conn.commit()

    # 2. Rebuild FTS5 Index
    print("Rebuilding FTS5 full-text index...")
    try:
        from db_schema import rebuild_fts
        fts_count = rebuild_fts(db_path)
        print(f"FTS5 index rebuilt successfully ({fts_count} records).")
    except Exception as e:
        print(f"Warning: could not rebuild FTS5 index: {e}")

    # 3. Update raw JSONL
    if os.path.exists(jsonl_path):
        print("Updating raw JSONL file...")
        updated_jsonl_count = 0
        temp_jsonl_path = jsonl_path + ".tmp"
        with open(jsonl_path, "r", encoding="utf-8") as in_f, open(temp_jsonl_path, "w", encoding="utf-8") as out_f:
            for line in in_f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    slug = record.get("slug")
                    if slug in updated_map:
                        record["ai_summary"] = updated_map[slug]
                        updated_jsonl_count += 1
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    out_f.write(line)
        os.replace(temp_jsonl_path, jsonl_path)
        print(f"Updated {updated_jsonl_count} records in {jsonl_path}.")

    # 4. Final Verification
    cursor.execute("SELECT id, slug, name, ai_summary FROM companies")
    all_rows = cursor.fetchall()
    conn.close()

    total_time = time.time() - start_time
    valid_count = sum(1 for r in all_rows if r[3] and not is_broken_summary(r[3]))
    broken_remaining = sum(1 for r in all_rows if is_broken_summary(r[3]))
    null_count = sum(1 for r in all_rows if not r[3])

    print("\n" + "=" * 60)
    print("AI SUMMARY REPAIR COMPLETE")
    print(f"Total time: {total_time:.1f}s")
    print(f"Total companies: {len(all_rows)}")
    print(f"Valid ai_summary with sentiment data: {valid_count}")
    print(f"Empty/Null ai_summary (fallback to description): {null_count}")
    print(f"Broken ai_summary remaining: {broken_remaining} (Target: 0)")
    print("=" * 60 + "\n")

    return {
        'total': len(all_rows),
        'valid': valid_count,
        'null': null_count,
        'broken_remaining': broken_remaining,
        'time': total_time
    }


if __name__ == "__main__":
    chmod_self = os.path.abspath(__file__)
    os.chmod(chmod_self, 0o755)
    fix_all_summaries()
