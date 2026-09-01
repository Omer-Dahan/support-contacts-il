import requests
import json
import re
from urllib.parse import unquote

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

def parse_company_page(slug, html, url=None):
    if url is None:
        url = f"https://sherutplus.com/{slug}"
        
    result = {
        'slug': slug,
        'url': url,
        'name': None,
        'legal_name': None,
        'company_id': None,
        'category': None,
        'description': None,
        'logo_url': None,
        'website_url': None,
        'social_links': [],
        'company_reg_id': None,
        'phones': [],      # list of dicts {number, label, purpose, is_primary, kind}
        'emails': [],      # list of dicts {email, label, contact_type}
        'whatsapp': [],    # list of dicts {url, phone}
        'hours': [],       # list of dicts or strings
        'branches': [],    # list of dicts
        'metrics': {},     # dict of metric fields
        'ai_summary': None,
        'accessibility': {},
        'faqs': [],
    }

    # 1. Parse JSON-LD scripts
    ld_jsons = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for ld_text in ld_jsons:
        try:
            ld = json.loads(ld_text)
            graph = ld.get('@graph', [ld] if isinstance(ld, dict) else [])
            for item in graph:
                if not isinstance(item, dict):
                    continue
                itype = item.get('@type')
                
                # Organization (Company)
                if itype == 'Organization' and item.get('@id') != 'https://sherutplus.com#organization' and item.get('name') != 'שירות פלוס':
                    result['name'] = item.get('name') or result['name']
                    result['legal_name'] = item.get('alternateName') or item.get('legalName') or result['legal_name']
                    result['description'] = item.get('description') or result['description']
                    result['logo_url'] = item.get('logo') or item.get('image') or result['logo_url']
                    
                    if item.get('identifier'):
                        result['company_reg_id'] = str(item.get('identifier')).strip()
                        
                    same_as = item.get('sameAs', [])
                    if isinstance(same_as, list):
                        for s in same_as:
                            if not isinstance(s, str): continue
                            if any(d in s for d in ['facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok']):
                                result['social_links'].append(s)
                            elif not result['website_url'] and s.startswith('http'):
                                result['website_url'] = s
                                
                    if item.get('telephone'):
                        result['phones'].append({
                            'number': str(item.get('telephone')).strip(),
                            'label': 'ראשי',
                            'purpose': 'service',
                            'is_primary': True,
                            'kind': 'phone'
                        })
                    if item.get('email'):
                        result['emails'].append({
                            'email': str(item.get('email')).strip(),
                            'label': 'ראשי',
                            'contact_type': 'general'
                        })
                        
                    # contactPoint
                    cps = item.get('contactPoint', [])
                    if isinstance(cps, dict):
                        cps = [cps]
                    for cp in cps:
                        if not isinstance(cp, dict):
                            continue
                        c_name = cp.get('name', '') or ''
                        c_type = cp.get('contactType', '') or ''
                        tel = cp.get('telephone')
                        email = cp.get('email')
                        cp_url = cp.get('url', '')
                        
                        if (cp_url and 'wa.me' in cp_url) or 'WhatsApp' in c_name:
                            result['whatsapp'].append({
                                'url': cp_url or f"https://wa.me/{tel}" if tel else None,
                                'phone': tel
                            })
                        elif tel:
                            result['phones'].append({
                                'number': str(tel).strip(),
                                'label': c_name or c_type or 'שירות',
                                'purpose': 'support' if 'support' in c_type else 'service',
                                'is_primary': False,
                                'kind': 'phone'
                            })
                        if email:
                            result['emails'].append({
                                'email': str(email).strip(),
                                'label': c_name or c_type or 'שירות',
                                'contact_type': c_type
                            })
                            
                    # openingHoursSpecification
                    ohs = item.get('openingHoursSpecification', [])
                    if isinstance(ohs, dict):
                        ohs = [ohs]
                    for oh in ohs:
                        if isinstance(oh, dict):
                            result['hours'].append({
                                'days': oh.get('dayOfWeek'),
                                'opens': oh.get('opens'),
                                'closes': oh.get('closes')
                            })
                            
                    # location (branches)
                    locs = item.get('location', [])
                    if isinstance(locs, dict):
                        locs = [locs]
                    for loc in locs:
                        if isinstance(loc, dict):
                            addr = loc.get('address')
                            street = addr.get('streetAddress') if isinstance(addr, dict) else (addr if isinstance(addr, str) else None)
                            city = addr.get('addressLocality') if isinstance(addr, dict) else None
                            result['branches'].append({
                                'name': loc.get('name'),
                                'address': street,
                                'city': city,
                                'phone': loc.get('telephone'),
                                'geo': loc.get('geo')
                            })
                            
                elif itype == 'BreadcrumbList':
                    elements = item.get('itemListElement', [])
                    if len(elements) >= 2:
                        cat_item = elements[1]
                        if isinstance(cat_item, dict) and 'name' in cat_item:
                            result['category'] = cat_item.get('name')
                            
                elif itype == 'FAQPage':
                    main_entities = item.get('mainEntity', [])
                    if isinstance(main_entities, list):
                        for q in main_entities:
                            if isinstance(q, dict):
                                q_name = q.get('name')
                                a_text = q.get('acceptedAnswer', {}).get('text') if isinstance(q.get('acceptedAnswer'), dict) else None
                                if q_name and a_text:
                                    result['faqs'].append({'question': q_name, 'answer': a_text})
                                    
                elif itype == 'HowTo':
                    steps = item.get('step', [])
                    if isinstance(steps, list):
                        for st in steps:
                            if not isinstance(st, dict): continue
                            st_url = st.get('url', '')
                            st_name = st.get('name', '')
                            if 'wa.me' in st_url:
                                result['whatsapp'].append({'url': st_url, 'label': st_name})
                            elif st_url.startswith('mailto:'):
                                result['emails'].append({'email': st_url.replace('mailto:', '').strip(), 'label': st_name, 'contact_type': 'quick_contact'})
                            elif st_url.startswith('tel:'):
                                result['phones'].append({'number': st_url.replace('tel:', '').strip(), 'label': st_name, 'purpose': 'quick_contact', 'is_primary': False, 'kind': 'phone'})
        except Exception as e:
            pass

    # 2. Parse React Server Components (self.__next_f)
    next_f_chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)', html, re.DOTALL)
    full_rsc = ""
    for chunk in next_f_chunks:
        try:
            full_rsc += json.loads('"' + chunk + '"')
        except Exception:
            full_rsc += chunk

    # Company metadata
    m_name = re.search(r'\"companyName\":\s*\"([^\"]+)\"', full_rsc)
    if m_name and not result['name']:
        result['name'] = m_name.group(1)
        
    m_cid = re.search(r'\"companyId\":\s*\"([^\"]+)\"', full_rsc)
    if m_cid:
        result['company_id'] = m_cid.group(1)
        
    m_color = re.search(r'\"brandColor\":\s*\"([^\"]+)\"', full_rsc)
    if m_color:
        result['brand_color'] = m_color.group(1)

    # RSC Phones
    for m in re.finditer(r'\"phones\":\s*(\[\{.*?\}\])', full_rsc):
        try:
            phones_arr = json.loads(m.group(1))
            for p in phones_arr:
                if isinstance(p, dict) and p.get('number'):
                    result['phones'].append({
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
                    result['branches'].append({
                        'name': b.get('name'),
                        'city': b.get('city'),
                        'address': b.get('address'),
                        'phone': b.get('phone'),
                        'email': b.get('email'),
                        'hours': b.get('hours')
                    })
        except Exception:
            pass

    # RSC Metrics
    m_resp = re.search(r'\"responseRate\":\s*([0-9.]+)', full_rsc)
    if m_resp: result['metrics']['responseRate'] = float(m_resp.group(1))
    m_unans = re.search(r'\"unansweredRate\":\s*([0-9.]+)', full_rsc)
    if m_unans: result['metrics']['unansweredRate'] = float(m_unans.group(1))
    m_avghr = re.search(r'\"avgResponseHours\":\s*([0-9.]+)', full_rsc)
    if m_avghr: result['metrics']['avgResponseHours'] = float(m_avghr.group(1))
    m_calm = re.search(r'\"calmPct\":\s*([0-9.]+)', full_rsc)
    if m_calm: result['metrics']['calmPct'] = float(m_calm.group(1))
    m_angry = re.search(r'\"angryPct\":\s*([0-9.]+)', full_rsc)
    if m_angry: result['metrics']['angryPct'] = float(m_angry.group(1))

    # Accessibility in RSC
    m_acc_phone = re.search(r'\"accessibility\"[^\}]*?\"phone\":\s*\"([^\"]+)\"', full_rsc)
    m_acc_email = re.search(r'\"accessibility\"[^\}]*?\"email\":\s*\"([^\"]+)\"', full_rsc)
    if m_acc_phone or m_acc_email:
        acc_info = {}
        if m_acc_phone: acc_info['phone'] = m_acc_phone.group(1)
        if m_acc_email: acc_info['email'] = m_acc_email.group(1)
        result['accessibility'] = acc_info

    # AI Summary
    m_ai = re.search(r'\"aiSummaryText\":\s*\"([^\"]+)\"', full_rsc)
    if m_ai:
        result['ai_summary'] = m_ai.group(1)

    # Deduplicate phones (by cleaned digits)
    dedup_phones = []
    seen_phone_nums = set()
    for p in result['phones']:
        num_clean = re.sub(r'[^0-9+*]', '', p['number'])
        if num_clean.startswith('972'):
            num_clean = '0' + num_clean[3:]
        elif num_clean.startswith('+972'):
            num_clean = '0' + num_clean[4:]
        if num_clean and num_clean not in seen_phone_nums:
            seen_phone_nums.add(num_clean)
            dedup_phones.append(p)
    result['phones'] = dedup_phones

    # Deduplicate emails
    dedup_emails = []
    seen_emails = set()
    for e in result['emails']:
        em = e['email'].lower().strip()
        if em and em not in seen_emails:
            seen_emails.add(em)
            dedup_emails.append(e)
    result['emails'] = dedup_emails

    # Deduplicate whatsapp
    dedup_wa = []
    seen_wa = set()
    for w in result['whatsapp']:
        target = w.get('url') or w.get('phone')
        if target and target not in seen_wa:
            seen_wa.add(target)
            dedup_wa.append(w)
    result['whatsapp'] = dedup_wa

    # Deduplicate branches
    dedup_branches = []
    seen_branches = set()
    for b in result['branches']:
        b_key = f"{b.get('name')}_{b.get('city')}_{b.get('address')}"
        if b_key not in seen_branches:
            seen_branches.add(b_key)
            dedup_branches.append(b)
    result['branches'] = dedup_branches

    return result

test_slugs = ['bezeq', 'klal', 'menora', 'home-center', 'ikea', 'ashmoret', 'hot', 'shufersal', 'el-al', 'wizz-air']
for s in test_slugs:
    r = requests.get(f'https://sherutplus.com/{s}', headers=headers, timeout=15)
    p = parse_company_page(s, r.text)
    print(f"=== {s} ===")
    print(f"  Name: {p['name']} | Legal: {p.get('legal_name')} | HP: {p.get('company_reg_id')} | Cat: {p['category']}")
    print(f"  Phones ({len(p['phones'])}): {[x['number'] for x in p['phones']]}")
    print(f"  Emails ({len(p['emails'])}): {[x['email'] for x in p['emails']]}")
    print(f"  WhatsApp ({len(p['whatsapp'])}): {[x.get('phone') or x.get('url') for x in p['whatsapp']]}")
    print(f"  Branches: {len(p['branches'])}, Hours: {len(p['hours'])}, FAQs: {len(p['faqs'])}, Metrics: {p['metrics']}")

