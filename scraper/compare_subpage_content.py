import requests
import json
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}

for path in ['ashmoret', 'legal/ashmoret', 'cancel/ashmoret', 'reviews/ashmoret', 'solutions/ashmoret']:
    url = f'https://sherutplus.com/{path}'
    r = requests.get(url, headers=headers)
    print(f"=== {url} (Status: {r.status_code}, Length: {len(r.text)}) ===")
    
    # check title / json-ld / phones
    titles = re.findall(r'<title>(.*?)</title>', r.text)
    print(f"  Title: {titles}")
    ld_jsons = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
    print(f"  JSON-LD blocks: {len(ld_jsons)}")
    phones = re.findall(r'"phones":\s*(\[\{.*?\}\])', r.text)
    print(f"  Phones match count: {len(phones)}")

