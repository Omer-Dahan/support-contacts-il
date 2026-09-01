import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://sherutplus.com/sitemap.xml', headers=headers, timeout=30)
root = ET.fromstring(r.content)
urls = [child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text.strip() 
        for child in root if child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc') is not None]

exclude_prefixes = [
    '/blog', '/coupons', '/category', '/case', '/complaints', '/branches',
    '/flights', '/buses', '/recalls', '/about', '/contact', '/business',
    '/terms', '/privacy', '/accessibility', '/app', '/how-it-works',
    '/companies', '/categories', '/search'
]

filtered_urls = []
for u in urls:
    path = urlparse(u).path
    if not path or path == '/':
        continue
    excluded = False
    for p in exclude_prefixes:
        if path == p or path.startswith(p + '/'):
            excluded = True
            break
    if not excluded:
        filtered_urls.append((u, path))

print(f"Total filtered URLs from sitemap: {len(filtered_urls)}")

# Check unique slugs from filtered_urls
slugs_from_subpaths = set()
slugs_root = set()

for u, p in filtered_urls:
    parts = p.strip('/').split('/')
    if len(parts) == 1:
        slugs_root.add(parts[0])
    elif len(parts) == 2:
        slugs_from_subpaths.add(parts[1])

print(f"Root slugs count: {len(slugs_root)}")
print(f"Subpath slugs count: {len(slugs_from_subpaths)}")
print(f"Subpath slugs not in root slugs: {len(slugs_from_subpaths - slugs_root)}")
if len(slugs_from_subpaths - slugs_root) > 0:
    print("Example subpath slugs not in root:", list(slugs_from_subpaths - slugs_root)[:10])

