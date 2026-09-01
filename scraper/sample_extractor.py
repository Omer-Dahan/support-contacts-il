import requests
import re
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

sample_slugs = ['bezeq', 'klal', 'ikea', 'shufersal', 'maccabi', 'elal', 'hot', 'electra', 'wizz-air', 'max']

def extract_company_data(slug, html):
    data = {
        'slug': slug,
        'name': None,
        'category': None,
        'company_id': None,
        'description': None,
        'logo_url': None,
        'website_url': None,
        'phones': [],
        'emails': [],
        'whatsapp': [],
        'hours': [],
        'addresses': [],
        'branches': [],
        'metrics': {},
        'raw_props': {}
    }
    
    # 1. Try to extract JSON-LD
    ld_jsons = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for ld_text in ld_jsons:
        try:
            ld = json.loads(ld_text)
            # LD graph
            graph = ld.get('@graph', [ld] if isinstance(ld, dict) else [])
            for item in graph:
                if not isinstance(item, dict):
                    continue
                item_type = item.get('@type')
                if item_type == 'Organization' and 'sherutplus.com' not in item.get('url', ''):
                    data['name'] = item.get('name') or data['name']
                    data['description'] = item.get('description') or data['description']
                    data['website_url'] = item.get('url') or data['website_url']
                    data['logo_url'] = item.get('logo') or data['logo_url']
                    
                    # contactPoint
                    cps = item.get('contactPoint', [])
                    if isinstance(cps, dict):
                        cps = [cps]
                    for cp in cps:
                        if isinstance(cp, dict):
                            num = cp.get('telephone')
                            email = cp.get('email')
                            c_type = cp.get('contactType')
                            name = cp.get('name')
                            url = cp.get('url')
                            if num:
                                data['phones'].append({'number': num, 'label': name or c_type, 'type': 'ld_phone'})
                            if email:
                                data['emails'].append({'email': email, 'label': name or c_type})
                            if url and 'wa.me' in url:
                                data['whatsapp'].append({'url': url, 'telephone': num})
                                
                    # locations
                    locs = item.get('location', [])
                    if isinstance(locs, dict):
                        locs = [locs]
                    for loc in locs:
                        if isinstance(loc, dict):
                            data['addresses'].append(loc)
                            
                elif item_type == 'BreadcrumbList':
                    elements = item.get('itemListElement', [])
                    # Usually: 1=חברות, 2=category, 3=company
                    if len(elements) >= 2:
                        cat_item = elements[1]
                        if isinstance(cat_item, dict) and 'name' in cat_item:
                            data['category'] = cat_item.get('name')
        except Exception as e:
            pass

    # 2. Extract from RSC (self.__next_f)
    next_f_chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)', html, re.DOTALL)
    full_rsc = ""
    for chunk in next_f_chunks:
        try:
            full_rsc += json.loads('"' + chunk + '"')
        except Exception:
            full_rsc += chunk
            
    # Search for specific props in RSC
    # Top company metadata
    m_comp = re.search(r'\"companyName\":\s*\"([^\"]+)\"', full_rsc)
    if m_comp and not data['name']:
        data['name'] = m_comp.group(1)
        
    m_comp_id = re.search(r'\"companyId\":\s*\"([^\"]+)\"', full_rsc)
    if m_comp_id:
        data['company_id'] = m_comp_id.group(1)
        
    m_phones = re.search(r'\"phones\":\s*(\[\{.*?\}\])', full_rsc)
    if m_phones:
        try:
            rsc_phones = json.loads(m_phones.group(1))
            data['rsc_phones'] = rsc_phones
        except Exception:
            pass

    m_branches = re.search(r'\"branches\":\s*(\[\{.*?\}\])', full_rsc)
    if m_branches:
        try:
            rsc_branches = json.loads(m_branches.group(1))
            data['rsc_branches'] = rsc_branches
        except Exception:
            pass

    m_channels = re.search(r'\"channels\":\s*(\[\{.*?\}\])', full_rsc)
    if m_channels:
        try:
            rsc_channels = json.loads(m_channels.group(1))
            data['rsc_channels'] = rsc_channels
        except Exception:
            pass

    return data

for slug in sample_slugs:
    url = f'https://sherutplus.com/{slug}'
    r = requests.get(url, headers=headers, timeout=15)
    parsed = extract_company_data(slug, r.text)
    print(f"=== {slug} ===")
    print(f"Name: {parsed['name']}, Category: {parsed['category']}, ID: {parsed['company_id']}")
    print(f"Phones from RSC: {parsed.get('rsc_phones')}")
    print(f"Phones from LD: {len(parsed['phones'])}, Emails: {len(parsed['emails'])}, Branches: {len(parsed.get('rsc_branches', []))}")
    print(f"Channels: {parsed.get('rsc_channels')}")

