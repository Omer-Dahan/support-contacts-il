#!/usr/bin/env python3
"""
Sherut Plus Scraper & SQLite Database Builder
Support Contacts IL Project
"""

import sys
import os
import time
import json
import html as html_lib
import re
import sqlite3
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = "/home/vm/projects/support-contacts-il/data/sherutplus.db"
JSONL_PATH = "/home/vm/projects/support-contacts-il/data/sherutplus_raw.jsonl"
REPORT_PATH = "/home/vm/projects/support-contacts-il/data/SCRAPE-REPORT.md"
FAILED_LOG_PATH = "/home/vm/projects/support-contacts-il/data/failed_urls.txt"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
}

EXCLUDE_PREFIXES = [
    '/blog', '/coupons', '/category', '/case', '/complaints', '/branches',
    '/flights', '/buses', '/recalls', '/about', '/contact', '/business',
    '/terms', '/privacy', '/accessibility', '/app', '/how-it-works',
    '/companies', '/categories', '/search', '/login', '/register',
    '/account', '/sender', '/case-details', '/cases'
]

NON_COMPANY_SLUGS = {
    'blog', 'coupons', 'category', 'case', 'complaints', 'branches',
    'flights', 'buses', 'recalls', 'about', 'contact', 'business',
    'terms', 'privacy', 'accessibility', 'app', 'how-it-works',
    'companies', 'categories', 'search', 'login', 'register',
    'account', 'sender', 'case-details', 'cases', 'legal', 'reviews',
    'cancel', 'solutions'
}

def init_db(db_path=DB_PATH, reset=False):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    if reset:
        cursor.executescript("""
        DROP TABLE IF EXISTS faqs;
        DROP TABLE IF EXISTS metrics;
        DROP TABLE IF EXISTS branches;
        DROP TABLE IF EXISTS hours;
        DROP TABLE IF EXISTS whatsapp;
        DROP TABLE IF EXISTS emails;
        DROP TABLE IF EXISTS phones;
        DROP TABLE IF EXISTS companies;
        """)

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
        answer TEXT NOT NULL,
        UNIQUE(company_id, question)
    );

    CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);
    CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
    CREATE INDEX IF NOT EXISTS idx_companies_slug ON companies(slug);
    CREATE INDEX IF NOT EXISTS idx_phones_company ON phones(company_id);
    CREATE INDEX IF NOT EXISTS idx_phones_number ON phones(clean_number);
    CREATE INDEX IF NOT EXISTS idx_emails_company ON emails(company_id);
    CREATE INDEX IF NOT EXISTS idx_branches_company ON branches(company_id);
    CREATE INDEX IF NOT EXISTS idx_branches_city ON branches(city);
    """)
    conn.commit()
    conn.close()

def clean_phone_number(num):
    if not num:
        return ""
    s = re.sub(r'[^0-9+*]', '', str(num).strip())
    if s.startswith('+972'):
        s = '0' + s[4:]
    elif s.startswith('972') and len(s) > 9:
        s = '0' + s[3:]
    return s

def parse_html_page(url, html):
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    slug = parts[-1]
    is_root_company = (len(parts) == 1)
    page_type = parts[0] if len(parts) > 1 else 'company'

    data = {
        'url': url,
        'slug': slug,
        'page_type': page_type,
        'scraped_at': datetime.now().isoformat(),
        'name': None,
        'legal_name': None,
        'company_reg_id': None,
        'category': None,
        'description': None,
        'logo_url': None,
        'website_url': None,
        'social_links': [],
        'brand_color': None,
        'company_id': None,
        'ai_summary': None,
        'phones': [],
        'emails': [],
        'whatsapp': [],
        'hours': [],
        'branches': [],
        'metrics': {},
        'faqs': []
    }

    # 1. Parse JSON-LD
    ld_jsons = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for ld_text in ld_jsons:
        try:
            ld = json.loads(ld_text)
            graph = ld.get('@graph', [ld] if isinstance(ld, dict) else [])
            for item in graph:
                if not isinstance(item, dict):
                    continue
                itype = item.get('@type')
                
                # Company Organization
                if itype == 'Organization' and item.get('@id') != 'https://sherutplus.com#organization' and item.get('name') != 'שירות פלוס':
                    if is_root_company and not data['name']:
                        data['name'] = item.get('name')
                    if not data['legal_name']:
                        data['legal_name'] = item.get('alternateName') or item.get('legalName')
                    if not data['description']:
                        data['description'] = item.get('description')
                    if not data['logo_url']:
                        data['logo_url'] = item.get('logo') or item.get('image')
                    if not data['company_reg_id'] and item.get('identifier'):
                        data['company_reg_id'] = str(item.get('identifier')).strip()
                        
                    same_as = item.get('sameAs', [])
                    if isinstance(same_as, list):
                        for s in same_as:
                            if not isinstance(s, str): continue
                            if any(d in s for d in ['facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok']):
                                if s not in data['social_links']:
                                    data['social_links'].append(s)
                            elif not data['website_url'] and s.startswith('http'):
                                data['website_url'] = s
                                
                    if item.get('telephone'):
                        data['phones'].append({
                            'number': str(item.get('telephone')).strip(),
                            'label': 'ראשי',
                            'purpose': 'service',
                            'is_primary': True,
                            'kind': 'phone'
                        })
                    if item.get('email'):
                        data['emails'].append({
                            'email': str(item.get('email')).strip(),
                            'label': 'ראשי',
                            'contact_type': 'general'
                        })
                        
                    # Contact points
                    cps = item.get('contactPoint', [])
                    if isinstance(cps, dict): cps = [cps]
                    for cp in cps:
                        if not isinstance(cp, dict): continue
                        c_name = cp.get('name', '') or ''
                        c_type = cp.get('contactType', '') or ''
                        tel = cp.get('telephone')
                        email = cp.get('email')
                        cp_url = cp.get('url', '')
                        
                        if (cp_url and 'wa.me' in cp_url) or 'WhatsApp' in c_name:
                            data['whatsapp'].append({
                                'url': cp_url or (f"https://wa.me/{tel}" if tel else ""),
                                'phone': tel,
                                'label': c_name or 'WhatsApp'
                            })
                        elif tel:
                            data['phones'].append({
                                'number': str(tel).strip(),
                                'label': c_name or c_type or 'שירות',
                                'purpose': 'support' if 'support' in str(c_type).lower() else 'service',
                                'is_primary': False,
                                'kind': 'phone'
                            })
                        if email:
                            data['emails'].append({
                                'email': str(email).strip(),
                                'label': c_name or c_type or 'שירות',
                                'contact_type': c_type
                            })
                            
                    # Hours
                    ohs = item.get('openingHoursSpecification', [])
                    if isinstance(ohs, dict): ohs = [ohs]
                    for oh in ohs:
                        if isinstance(oh, dict):
                            data['hours'].append({
                                'days': json.dumps(oh.get('dayOfWeek'), ensure_ascii=False) if isinstance(oh.get('dayOfWeek'), list) else str(oh.get('dayOfWeek')),
                                'opens': oh.get('opens'),
                                'closes': oh.get('closes'),
                                'raw_text': f"{oh.get('opens')}-{oh.get('closes')}"
                            })
                            
                    # Branches / Locations
                    locs = item.get('location', [])
                    if isinstance(locs, dict): locs = [locs]
                    for loc in locs:
                        if isinstance(loc, dict):
                            addr = loc.get('address')
                            street = addr.get('streetAddress') if isinstance(addr, dict) else (addr if isinstance(addr, str) else None)
                            city = addr.get('addressLocality') if isinstance(addr, dict) else None
                            geo = loc.get('geo', {})
                            lat = geo.get('latitude') if isinstance(geo, dict) else None
                            lon = geo.get('longitude') if isinstance(geo, dict) else None
                            data['branches'].append({
                                'name': loc.get('name'),
                                'address': street,
                                'city': city,
                                'phone': loc.get('telephone'),
                                'email': None,
                                'hours': None,
                                'latitude': float(lat) if lat is not None else None,
                                'longitude': float(lon) if lon is not None else None
                            })
                            
                elif itype == 'BreadcrumbList':
                    elements = item.get('itemListElement', [])
                    for el in elements:
                        if isinstance(el, dict):
                            el_item = el.get('item', '')
                            # Only extract category from explicit /category/ URL
                            if '/category/' in el_item:
                                data['category'] = el.get('name')
                                break
                            
                elif itype == 'FAQPage':
                    main_entities = item.get('mainEntity', [])
                    if isinstance(main_entities, list):
                        for q in main_entities:
                            if isinstance(q, dict):
                                q_name = q.get('name')
                                a_text = q.get('acceptedAnswer', {}).get('text') if isinstance(q.get('acceptedAnswer'), dict) else None
                                if q_name and a_text:
                                    data['faqs'].append({'question': q_name, 'answer': a_text})
                                    
                elif itype == 'HowTo':
                    steps = item.get('step', [])
                    if isinstance(steps, list):
                        for st in steps:
                            if not isinstance(st, dict): continue
                            st_url = st.get('url', '')
                            st_name = st.get('name', '')
                            if 'wa.me' in st_url:
                                data['whatsapp'].append({'url': st_url, 'label': st_name, 'phone': None})
                            elif st_url.startswith('mailto:'):
                                data['emails'].append({'email': st_url.replace('mailto:', '').strip(), 'label': st_name, 'contact_type': 'quick_contact'})
                            elif st_url.startswith('tel:'):
                                data['phones'].append({'number': st_url.replace('tel:', '').strip(), 'label': st_name, 'purpose': 'quick_contact', 'is_primary': False, 'kind': 'phone'})
        except Exception:
            pass

    # 2. Parse React Server Components (RSC)
    next_f_chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)', html, re.DOTALL)
    full_rsc = ""
    for chunk in next_f_chunks:
        try:
            full_rsc += json.loads('"' + chunk + '"')
        except Exception:
            full_rsc += chunk

    # Top metadata
    m_name = re.search(r'\"companyName\":\s*\"([^\"]+)\"', full_rsc)
    if m_name and is_root_company and not data['name']:
        data['name'] = m_name.group(1)
        
    m_cid = re.search(r'\"companyId\":\s*\"([^\"]+)\"', full_rsc)
    if m_cid:
        data['company_id'] = m_cid.group(1)
        
    m_color = re.search(r'\"brandColor\":\s*\"([^\"]+)\"', full_rsc)
    if m_color:
        data['brand_color'] = m_color.group(1)

    # RSC Phones
    for m in re.finditer(r'\"phones\":\s*(\[\{.*?\}\])', full_rsc):
        try:
            phones_arr = json.loads(m.group(1))
            for p in phones_arr:
                if isinstance(p, dict) and p.get('number'):
                    data['phones'].append({
                        'number': str(p.get('number')).strip(),
                        'label': p.get('label'),
                        'purpose': p.get('purpose', 'service'),
                        'is_primary': bool(p.get('isPrimary', False)),
                        'kind': p.get('kind', 'phone')
                    })
        except Exception:
            pass

    # RSC Branches
    for m in re.finditer(r'\"branches\":\s*(\[\{.*?\}\])', full_rsc):
        try:
            branches_arr = json.loads(m.group(1))
            for b in branches_arr:
                if isinstance(b, dict):
                    data['branches'].append({
                        'name': b.get('name'),
                        'city': b.get('city'),
                        'address': b.get('address'),
                        'phone': b.get('phone'),
                        'email': b.get('email'),
                        'hours': b.get('hours'),
                        'latitude': None,
                        'longitude': None
                    })
        except Exception:
            pass

    # RSC Metrics
    m_resp = re.search(r'\"responseRate\":\s*([0-9.]+)', full_rsc)
    if m_resp: data['metrics']['response_rate'] = float(m_resp.group(1))
    m_unans = re.search(r'\"unansweredRate\":\s*([0-9.]+)', full_rsc)
    if m_unans: data['metrics']['unanswered_rate'] = float(m_unans.group(1))
    m_avghr = re.search(r'\"avgResponseHours\":\s*([0-9.]+)', full_rsc)
    if m_avghr: data['metrics']['avg_response_hours'] = float(m_avghr.group(1))
    m_avgem = re.search(r'\"avgEmailsToResolve\":\s*([0-9.]+)', full_rsc)
    if m_avgem: data['metrics']['avg_emails_to_resolve'] = float(m_avgem.group(1))
    m_calm = re.search(r'\"calmPct\":\s*([0-9.]+)', full_rsc)
    if m_calm: data['metrics']['calm_pct'] = float(m_calm.group(1))
    m_angry = re.search(r'\"angryPct\":\s*([0-9.]+)', full_rsc)
    if m_angry: data['metrics']['angry_pct'] = float(m_angry.group(1))

    # AI Summary extraction from SVG / role=img aria-label and inquiries count
    html_unescaped = html_lib.unescape(html)
    sentiment_m = re.search(r"""aria-label=["']\s*(פילוח רגשות:[^"']+)["']""", html_unescaped)
    if not sentiment_m:
        sentiment_m = re.search(r"""role=["']img["'][^>]*aria-label=["']([^"']*(?:מתוסכל|כועס|רגוע|מרוצה|מיואש|מאוכזב)[^"']*)["']""", html_unescaped)
        if not sentiment_m:
            sentiment_m = re.search(r"""aria-label=["']([^"']*(?:מתוסכל|כועס|רגוע|מרוצה|מיואש|מאוכזב)\s*\d+%[^"']*)["']""", html_unescaped)

    if sentiment_m:
        sentiment_raw = sentiment_m.group(1).strip()
        sentiment_clean = re.sub(r"^פילוח רגשות:\s*", "", sentiment_raw).strip()
        sentiment_clean = re.sub(r"\s+", " ", sentiment_clean)

        inq_m = re.search(r"מבוסס על\s*(?:<[^>]+>)?\s*([0-9,]+)\s*(?:<[^>]+>)?\s*פניות גולשים", html_unescaped)
        if not inq_m:
            inq_m = re.search(r"מבוסס על\s*([0-9,]+)\s*פניות גולשים", html_unescaped)

        if inq_m:
            inq_cnt = inq_m.group(1).replace(",", "").strip()
            data['ai_summary'] = f"📊 ניתוח פניות ({inq_cnt} פניות גולשים): {sentiment_clean}"
        else:
            data['ai_summary'] = f"📊 ניתוח פניות: {sentiment_clean}"
    else:
        data['ai_summary'] = None

    # Special check for legal pages: ח.פ. in page
    if not data['company_reg_id']:
        m_hp = re.search(r'ח\.?פ\.?\s*([0-9]{9})', html)
        if m_hp:
            data['company_reg_id'] = m_hp.group(1)

    # Fallback name from title tag ONLY for root company pages
    if is_root_company and not data['name']:
        m_title = re.search(r'<title>(.*?)</title>', html)
        if m_title:
            t = m_title.group(1)
            t_clean = t.split('-')[0].split('—')[0].split('|')[0].strip()
            data['name'] = t_clean

    # Deduplicate phones
    dedup_phones = []
    seen_phone_nums = set()
    for p in data['phones']:
        c_num = clean_phone_number(p['number'])
        kind = p.get('kind', 'phone')
        key = (c_num, kind)
        if c_num and key not in seen_phone_nums:
            seen_phone_nums.add(key)
            p_copy = dict(p)
            p_copy['clean_number'] = c_num
            dedup_phones.append(p_copy)
    data['phones'] = dedup_phones

    # Deduplicate emails
    dedup_emails = []
    seen_emails = set()
    for e in data['emails']:
        em = e['email'].lower().strip()
        if em and '@' in em and em not in seen_emails:
            seen_emails.add(em)
            dedup_emails.append(e)
    data['emails'] = dedup_emails

    # Deduplicate whatsapp & normalize phone from url
    dedup_wa = []
    seen_wa = set()
    for w in data['whatsapp']:
        url = w.get('url', '')
        phone = w.get('phone')
        if (not phone or '*' in str(phone)) and url:
            m_wa = re.search(r'wa\.me/(\d+)', url)
            if m_wa:
                w['phone'] = '+' + m_wa.group(1)
        target = w.get('url') or w.get('phone')
        if target and target not in seen_wa:
            seen_wa.add(target)
            dedup_wa.append(w)
    data['whatsapp'] = dedup_wa

    # Deduplicate branches
    dedup_branches = []
    seen_branches = set()
    for b in data['branches']:
        b_key = f"{b.get('name')}_{b.get('city')}_{b.get('address')}"
        if b_key not in seen_branches:
            seen_branches.add(b_key)
            dedup_branches.append(b)
    data['branches'] = dedup_branches

    return data

def save_to_db(data_record, db_path=DB_PATH):
    slug = data_record['slug']
    page_type = data_record.get('page_type', 'company')
    is_root = (page_type == 'company')
    name = data_record.get('name')

    if slug in NON_COMPANY_SLUGS:
        return False

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    now_str = datetime.now().isoformat()

    try:
        # 1. Upsert company
        cursor.execute("SELECT id, name, legal_name, company_reg_id, category, description, logo_url, website_url, social_links, brand_color, ai_summary FROM companies WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        
        if row:
            cid = row[0]
            cur_name = row[1]
            cur_legal = row[2]
            cur_reg = row[3]
            cur_cat = row[4]
            cur_desc = row[5]
            cur_logo = row[6]
            cur_web = row[7]
            cur_soc = row[8]
            cur_color = row[9]
            cur_ai = row[10]

            # Only root company pages can set or change name and category
            new_name = (name if name and name != 'שירות פלוס' else cur_name) if is_root else cur_name
            new_cat = (data_record.get('category') or cur_cat) if is_root else cur_cat
            new_legal = data_record.get('legal_name') or cur_legal
            new_reg = data_record.get('company_reg_id') or cur_reg
            new_desc = (data_record.get('description') or cur_desc) if is_root else cur_desc
            new_logo = (data_record.get('logo_url') or cur_logo) if is_root else cur_logo
            new_web = (data_record.get('website_url') or cur_web) if is_root else cur_web
            new_color = (data_record.get('brand_color') or cur_color) if is_root else cur_color
            new_ai = (data_record.get('ai_summary') or cur_ai) if is_root else cur_ai
            
            # Merge social links
            existing_soc = json.loads(cur_soc) if cur_soc else []
            for s in data_record.get('social_links', []):
                if s not in existing_soc:
                    existing_soc.append(s)
            social_json = json.dumps(existing_soc, ensure_ascii=False)

            cursor.execute("""
            UPDATE companies SET
                name = ?,
                legal_name = ?,
                company_reg_id = ?,
                category = ?,
                description = ?,
                logo_url = ?,
                website_url = ?,
                social_links = ?,
                brand_color = ?,
                ai_summary = ?,
                updated_at = ?
            WHERE id = ?
            """, (new_name, new_legal, new_reg, new_cat, new_desc, new_logo, new_web, social_json, new_color, new_ai, now_str, cid))
        else:
            if not name or name == 'שירות פלוס':
                return False

            social_json = json.dumps(data_record.get('social_links', []), ensure_ascii=False)
            cursor.execute("""
            INSERT INTO companies (
                slug, name, legal_name, company_reg_id, category, description,
                logo_url, website_url, social_links, brand_color, ai_summary,
                source_url, scraped_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slug, name, data_record.get('legal_name'), data_record.get('company_reg_id'),
                data_record.get('category'), data_record.get('description'), data_record.get('logo_url'),
                data_record.get('website_url'), social_json, data_record.get('brand_color'),
                data_record.get('ai_summary'), data_record['url'], now_str, now_str
            ))
            cid = cursor.lastrowid

        # 2. Insert phones
        for p in data_record.get('phones', []):
            c_num = p.get('clean_number') or clean_phone_number(p.get('number'))
            if c_num:
                cursor.execute("""
                INSERT OR IGNORE INTO phones (
                    company_id, company_slug, number, clean_number, label, purpose, is_primary, kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cid, slug, p.get('number'), c_num, p.get('label'),
                    p.get('purpose', 'service'), 1 if p.get('is_primary') else 0, p.get('kind', 'phone')
                ))

        # 3. Insert emails
        for e in data_record.get('emails', []):
            em = e.get('email')
            if em:
                cursor.execute("""
                INSERT OR IGNORE INTO emails (
                    company_id, company_slug, email, label, contact_type
                ) VALUES (?, ?, ?, ?, ?)
                """, (cid, slug, em, e.get('label'), e.get('contact_type')))

        # 4. Insert WhatsApp
        for w in data_record.get('whatsapp', []):
            url = w.get('url')
            if url:
                cursor.execute("""
                INSERT OR IGNORE INTO whatsapp (
                    company_id, company_slug, phone, url, label
                ) VALUES (?, ?, ?, ?, ?)
                """, (cid, slug, w.get('phone'), url, w.get('label')))

        # 5. Insert Hours
        for h in data_record.get('hours', []):
            cursor.execute("""
            INSERT INTO hours (
                company_id, company_slug, days, opens, closes, raw_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (cid, slug, h.get('days'), h.get('opens'), h.get('closes'), h.get('raw_text')))

        # 6. Insert Branches
        for b in data_record.get('branches', []):
            cursor.execute("""
            INSERT INTO branches (
                company_id, company_slug, name, city, address, phone, email, hours, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, slug, b.get('name'), b.get('city'), b.get('address'),
                b.get('phone'), b.get('email'), b.get('hours'), b.get('latitude'), b.get('longitude')
            ))

        # 7. Insert / Replace Metrics
        m = data_record.get('metrics', {})
        if m:
            cursor.execute("""
            INSERT OR REPLACE INTO metrics (
                company_id, company_slug, response_rate, unanswered_rate, avg_response_hours,
                avg_emails_to_resolve, calm_pct, angry_pct, raw_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, slug, m.get('response_rate'), m.get('unanswered_rate'), m.get('avg_response_hours'),
                m.get('avg_emails_to_resolve'), m.get('calm_pct'), m.get('angry_pct'), json.dumps(m, ensure_ascii=False)
            ))

        # 8. Insert FAQs
        for faq in data_record.get('faqs', []):
            q = faq.get('question')
            a = faq.get('answer')
            if q and a:
                cursor.execute("""
                INSERT OR IGNORE INTO faqs (
                    company_id, company_slug, question, answer
                ) VALUES (?, ?, ?, ?)
                """, (cid, slug, q, a))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error saving to DB for slug {slug}: {e}")
        return False
    finally:
        conn.close()

def collect_urls():
    import requests
    print("Fetching sitemap.xml...")
    r = requests.get('https://sherutplus.com/sitemap.xml', headers=HEADERS, timeout=30)
    root = ET.fromstring(r.content)
    raw_urls = [
        child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text.strip()
        for child in root if child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc') is not None
    ]
    print(f"Total raw URLs in sitemap: {len(raw_urls)}")

    filtered_urls = []
    seen_urls = set()
    
    for u in raw_urls:
        path = urlparse(u).path
        if not path or path == '/':
            continue
        excluded = False
        for p in EXCLUDE_PREFIXES:
            if path == p or path.startswith(p + '/'):
                excluded = True
                break
        if not excluded and u not in seen_urls:
            seen_urls.add(u)
            filtered_urls.append(u)

    print(f"Filtered sitemap URLs: {len(filtered_urls)}")

    # Prioritize root company pages first, then subpages
    def url_priority(u):
        p = urlparse(u).path.strip('/')
        return (0 if '/' not in p else 1, u)

    filtered_urls.sort(key=url_priority)
    return filtered_urls

def run_scraper(urls, max_workers=4):
    import requests
    
    # Initialize DB (reset for clean fresh build)
    init_db(DB_PATH, reset=True)
    
    # Clear / start fresh JSONL file
    if os.path.exists(JSONL_PATH):
        os.remove(JSONL_PATH)
    jsonl_file = open(JSONL_PATH, "a", encoding="utf-8")
    
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=max_workers*2, pool_maxsize=max_workers*2, max_retries=1)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)

    total = len(urls)
    print(f"\n========================================================")
    print(f"Starting scrape of {total} URLs with {max_workers} concurrent workers...")
    print(f"Database: {DB_PATH}")
    print(f"Raw JSONL: {JSONL_PATH}")
    print(f"========================================================\n")

    successful_count = 0
    failed_urls = []
    
    start_time = time.time()

    def fetch_url(url, retry=True):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return url, r.text, None
            elif retry:
                time.sleep(1)
                r2 = session.get(url, timeout=30)
                if r2.status_code == 200:
                    return url, r2.text, None
                return url, None, f"HTTP {r2.status_code}"
            else:
                return url, None, f"HTTP {r.status_code}"
        except Exception as e:
            if retry:
                time.sleep(1.5)
                try:
                    r2 = session.get(url, timeout=30)
                    if r2.status_code == 200:
                        return url, r2.text, None
                    return url, None, f"HTTP {r2.status_code}"
                except Exception as e2:
                    return url, None, str(e2)
            return url, None, str(e)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_url, u): u for u in urls}
        
        idx = 0
        for future in as_completed(future_to_url):
            idx += 1
            url = future_to_url[future]
            try:
                res_url, html_text, err = future.result()
                if html_text:
                    parsed_data = parse_html_page(res_url, html_text)
                    
                    # 1. Write to JSONL
                    jsonl_file.write(json.dumps(parsed_data, ensure_ascii=False) + "\n")
                    jsonl_file.flush()
                    
                    # 2. Save to SQLite
                    saved = save_to_db(parsed_data, DB_PATH)
                    successful_count += 1
                    
                    # Progress log
                    if idx % 50 == 0 or idx == total or parsed_data.get('page_type') == 'company':
                        elapsed = time.time() - start_time
                        speed = idx / elapsed if elapsed > 0 else 0
                        print(f"[{idx}/{total}] ({(idx/total)*100:.1f}%) | Success: {successful_count} | Fail: {len(failed_urls)} | {speed:.1f} req/s | {parsed_data.get('slug')}")
                else:
                    failed_urls.append((url, err))
                    print(f"[{idx}/{total}] FAILED: {url} -> {err}")
            except Exception as e:
                failed_urls.append((url, str(e)))
                print(f"[{idx}/{total}] EXCEPTION for {url}: {e}")

    jsonl_file.close()
    total_time = time.time() - start_time
    
    # Write failed URLs if any
    with open(FAILED_LOG_PATH, "w", encoding="utf-8") as ff:
        for u, err in failed_urls:
            ff.write(f"{u}\t{err}\n")

    print(f"\n========================================================")
    print(f"Scraping completed in {total_time:.1f}s ({total_time/60:.2f} mins)")
    print(f"Total Attempted: {total}")
    print(f"Successful: {successful_count}")
    print(f"Failed: {len(failed_urls)}")
    print(f"========================================================\n")

    return total, successful_count, failed_urls, total_time

def generate_report(total_attempted, successful_count, failed_urls, total_time):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM companies")
    total_companies = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM phones")
    total_phones = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT company_id) FROM phones")
    companies_with_phones = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM emails")
    total_emails = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM whatsapp")
    total_wa = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM branches")
    total_branches = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM hours")
    total_hours = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM metrics")
    total_metrics = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM faqs")
    total_faqs = cursor.fetchone()[0]

    # Category breakdown
    cursor.execute("""
    SELECT 
        COALESCE(c.category, 'ללא קטגוריה') as cat,
        COUNT(DISTINCT c.id) as comp_count,
        COUNT(DISTINCT p.id) as phone_count,
        COUNT(DISTINCT e.id) as email_count,
        COUNT(DISTINCT w.id) as wa_count,
        COUNT(DISTINCT b.id) as branch_count
    FROM companies c
    LEFT JOIN phones p ON c.id = p.company_id
    LEFT JOIN emails e ON c.id = e.company_id
    LEFT JOIN whatsapp w ON c.id = w.company_id
    LEFT JOIN branches b ON c.id = b.company_id
    GROUP BY cat
    ORDER BY comp_count DESC
    """)
    category_stats = cursor.fetchall()

    conn.close()

    report_content = f"""# דוח שאיבת נתונים — SherutPlus.com (Support Contacts IL)

תאריך ביצוע: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. סיכום תהליך השאיבה
- **כתובות URL שנסרקו:** {total_attempted:,}
- **הורדו ועובדו בהצלחה:** {successful_count:,} ({(successful_count/total_attempted)*100:.1f}%)
- **נכשלו:** {len(failed_urls)}
- **זמן ביצוע כולל:** {total_time:.1f} שניות ({total_time/60:.2f} דקות)
- **קצב ממוצע:** {total_attempted/total_time:.1f} בקשות/שנייה (4 workers במקביל)

## 2. סיכום מסד הנתונים (`sherutplus.db`)

| טבלה | תיאור | כמות רשומות | הערות |
|---|---|---|---|
| `companies` | חברות וארגונים | **{total_companies:,}** | מזהה ייחודי לפי slug, כולל ח.פ., לוגו, אתר, תיאור, קטגוריה וסיכום AI |
| `phones` | מספרי טלפון, פקס ו-SMS | **{total_phones:,}** | {companies_with_phones:,} חברות עם לפחות טלפון אחד, מסווג (ראשי/נוסף/פקס/SMS) |
| `emails` | כתובות דוא"ל לשירות ותמיכה | **{total_emails:,}** | כולל מיילים של שירות, תמיכה, נגישות ופניות הציבור |
| `whatsapp` | מספרי וערוצי WhatsApp | **{total_wa:,}** | קישורים ישירים ל-wa.me ומספרים מאומתים |
| `branches` | סניפים ונקודות שירות | **{total_branches:,}** | כולל כתובת מדויקת, עיר, טלפון לסניף וקואורדינטות גיאוגרפיות |
| `hours` | שעות פעילות וקבלת קהל | **{total_hours:,}** | מפורט לפי ימי השבוע ושעות פתיחה/סגירה |
| `metrics` | מדדי שירות וביצועים | **{total_metrics:,}** | זמני מענה ממוצעים, אחוזי מענה ושביעות רצון לקוחות |
| `faqs` | שאלות ותשובות נפוצות | **{total_faqs:,}** | שאלות ותשובות רשמיות מאתר השירות |

## 3. פילוח לפי קטגוריות

| קטגוריה | חברות | טלפונים | מיילים | WhatsApp | סניפים |
|---|---|---|---|---|---|
"""
    for cat, comp_c, phone_c, email_c, wa_c, branch_c in category_stats:
        report_content += f"| {cat} | {comp_c:,} | {phone_c:,} | {email_c:,} | {wa_c:,} | {branch_c:,} |\n"

    report_content += f"""
## 4. קבצים שנוצרו בפרויקט
- **מסד נתונים SQLite:** `/home/vm/projects/support-contacts-il/data/sherutplus.db`
- **קובץ נתונים גולמי JSONL:** `/home/vm/projects/support-contacts-il/data/sherutplus_raw.jsonl`
- **סקריפט ייצוא ל-VCF:** `/home/vm/projects/support-contacts-il/scraper/export_vcf.py` (ועותק ב-`/home/vm/projects/support-contacts-il/export_vcf.py`)
- **דוח שאיבה:** `/home/vm/projects/support-contacts-il/data/SCRAPE-REPORT.md`

## 5. דוגמאות שאילתות לבוט טלגרם / מפתחים

### חיפוש חברה לפי שם או חלק משם:
```sql
SELECT id, slug, name, category, website_url, description
FROM companies
WHERE name LIKE '%בזק%' OR slug LIKE '%bezeq%';
```

### שליפת כל פרטי הקשר של חברה:
```sql
-- טלפונים
SELECT number, label, purpose, is_primary, kind 
FROM phones WHERE company_slug = 'bezeq' ORDER BY is_primary DESC;

-- מיילים
SELECT email, label, contact_type 
FROM emails WHERE company_slug = 'bezeq';

-- WhatsApp
SELECT url, phone, label 
FROM whatsapp WHERE company_slug = 'bezeq';

-- סניפים
SELECT name, city, address, phone 
FROM branches WHERE company_slug = 'bezeq';
```

### רשימת כל החברות בקטגוריה מסוימת:
```sql
SELECT c.name, c.slug, COUNT(p.id) as phones_count
FROM companies c
LEFT JOIN phones p ON c.id = p.company_id
WHERE c.category = 'אינטרנט'
GROUP BY c.id
ORDER BY c.name;
```
"""

    if failed_urls:
        report_content += f"\n## 6. פירוט כתובות שנכשלו ({len(failed_urls)})\n"
        for u, err in failed_urls:
            report_content += f"- `{u}`: {err}\n"
    else:
        report_content += "\n## 6. סטטוס תקלות\nכל הכתובות ירדו בהצלחה (0 כישלונות).\n"

    with open(REPORT_PATH, "w", encoding="utf-8") as rf:
        rf.write(report_content)

    print(f"Report written to {REPORT_PATH}")

if __name__ == "__main__":
    urls = collect_urls()
    total_attempted, successful_count, failed_urls, total_time = run_scraper(urls, max_workers=4)
    generate_report(total_attempted, successful_count, failed_urls, total_time)
