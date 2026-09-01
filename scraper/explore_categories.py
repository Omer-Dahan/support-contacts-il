import requests
import re
from urllib.parse import unquote

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

# 1. Fetch /categories
r_cats = requests.get('https://sherutplus.com/categories', headers=headers, timeout=30)
cat_urls = re.findall(r'href="(/category/[^"]+)"', r_cats.text)

print(f"Discovered {len(cat_urls)} category URLs")
all_category_slugs = set()
for cu in set(cat_urls):
    cat_res = requests.get('https://sherutplus.com' + cu, headers=headers, timeout=15)
    links = set(re.findall(r'href="\/([a-zA-Z0-9_-]+)"', cat_res.text))
    # filter out static pages
    links = {l for l in links if l not in ['blog', 'coupons', 'category', 'case', 'complaints', 'branches', 'flights', 'buses', 'recalls', 'about', 'contact', 'business', 'terms', 'privacy', 'accessibility', 'app', 'how-it-works', 'companies', 'categories', 'search', 'legal', 'reviews', 'cancel', 'solutions']}
    print(f"Category {unquote(cu)}: {len(links)} company links")
    all_category_slugs.update(links)

print(f"Total distinct company slugs from category pages: {len(all_category_slugs)}")

