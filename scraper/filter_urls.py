import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://sherutplus.com/sitemap.xml', headers=headers, timeout=30)
root = ET.fromstring(r.content)
urls = [child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text.strip() 
        for child in root if child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc') is not None]

# User's exact exclude list:
# הסר /blog /coupons /category /case /complaints /branches /flights /buses /recalls /about /contact /business /terms /privacy /accessibility /app /how-it-works /companies /categories /search, וגם דף הבית

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

print(f"Total URLs in sitemap: {len(urls)}")
print(f"Filtered URLs matching user instructions: {len(filtered_urls)}")

# Check path patterns in filtered_urls
from collections import Counter
patterns = Counter([p.split('/')[1] if len(p.split('/')) > 1 else 'root' for _, p in filtered_urls])
print("Path types in filtered:", patterns)

# Root level URLs:
root_urls = [u for u, p in filtered_urls if len(p.strip('/').split('/')) == 1]
print(f"Root level company URLs: {len(root_urls)}")

# What are the other paths?
other_urls = [(u, p) for u, p in filtered_urls if len(p.strip('/').split('/')) > 1]
print(f"Subpath URLs: {len(other_urls)}")
print("Sample other URLs:", other_urls[:10])

