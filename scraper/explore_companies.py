import requests
import re
import json
import xml.etree.ElementTree as ET

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

# Check /companies
r_comp = requests.get('https://sherutplus.com/companies', headers=headers, timeout=30)
# Find all links in /companies
comp_links = set(re.findall(r'href="\/([a-zA-Z0-9_-]+)"', r_comp.text))
print(f"Company slugs found on /companies page: {len(comp_links)}")

# Check category pages from /categories
r_cats = requests.get('https://sherutplus.com/categories', headers=headers, timeout=30)
cat_links = set(re.findall(r'href="\/category\/([^"]+)"', r_cats.text))
print(f"Categories found on /categories: {len(cat_links)}")

# Extract all company slugs referenced across sitemap
r_sitemap = requests.get('https://sherutplus.com/sitemap.xml', headers=headers, timeout=30)
root = ET.fromstring(r_sitemap.content)
sitemap_urls = [child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text.strip() 
                for child in root if child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc') is not None]

all_company_slugs = set()
for u in sitemap_urls:
    path = u.replace('https://sherutplus.com/', '').replace('https://sherutplus.com', '').strip('/')
    if not path:
        continue
    parts = path.split('/')
    if len(parts) == 1:
        # single segment
        if parts[0] not in ['blog', 'coupons', 'category', 'case', 'complaints', 'branches', 'flights', 'buses', 'recalls', 'about', 'contact', 'business', 'terms', 'privacy', 'accessibility', 'app', 'how-it-works', 'companies', 'categories', 'search', 'legal', 'reviews', 'cancel', 'solutions']:
            all_company_slugs.add(parts[0])
    elif len(parts) == 2:
        # e.g. branches/bezeq, legal/shefa-hafakot, reviews/pampers, cancel/bezeq
        if parts[0] in ['branches', 'legal', 'reviews', 'cancel', 'solutions', 'complaints']:
            all_company_slugs.add(parts[1])

print(f"Total unique company slugs discovered from sitemap paths: {len(all_company_slugs)}")

# Let's check how many company slugs are in /companies vs discovered
print(f"Slugs in /companies but not in all_company_slugs: {len(comp_links - all_company_slugs)}")
print(f"Slugs in all_company_slugs but not in /companies: {len(all_company_slugs - comp_links)}")

# Total combined unique companies
combined = all_company_slugs.union(comp_links)
# remove non-companies from combined
non_company_words = {'blog', 'coupons', 'category', 'case', 'complaints', 'branches', 'flights', 'buses', 'recalls', 'about', 'contact', 'business', 'terms', 'privacy', 'accessibility', 'app', 'how-it-works', 'companies', 'categories', 'search', 'legal', 'reviews', 'cancel', 'solutions'}
combined = combined - non_company_words
print(f"Total combined unique company slugs: {len(combined)}")

