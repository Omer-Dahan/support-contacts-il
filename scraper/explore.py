import requests
import re
import json
import xml.etree.ElementTree as ET
from collections import Counter

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

# 1. Sitemap
r_sitemap = requests.get('https://sherutplus.com/sitemap.xml', headers=headers, timeout=30)
root = ET.fromstring(r_sitemap.content)
urls = [child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text.strip() 
        for child in root if child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc') is not None]

print(f"Total sitemap URLs: {len(urls)}")

# 2. Check /companies
r_comp = requests.get('https://sherutplus.com/companies', headers=headers, timeout=30)
print(f"/companies status: {r_comp.status_code}, length: {len(r_comp.text)}")

# Check category pages
r_cat = requests.get('https://sherutplus.com/categories', headers=headers, timeout=30)
print(f"/categories status: {r_cat.status_code}, length: {len(r_cat.text)}")

# Check robots.txt
r_rob = requests.get('https://sherutplus.com/robots.txt', headers=headers, timeout=30)
print("robots.txt:\n", r_rob.text)

# Let's inspect paths from sitemap
paths = [u.replace('https://sherutplus.com/', '').replace('https://sherutplus.com', '').strip('/') for u in urls]
first_parts = Counter([p.split('/')[0] if '/' in p else '<root>' for p in paths if p])
print("First parts in sitemap:")
for k, v in first_parts.most_common():
    print(f"  {k}: {v}")

