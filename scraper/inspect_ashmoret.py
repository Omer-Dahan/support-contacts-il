import requests
import json
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
r = requests.get('https://sherutplus.com/ashmoret', headers=headers)
html = r.text

print(f"Ashmoret length: {len(html)}")

# Check JSON-LD
ld_jsons = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
for i, ld in enumerate(ld_jsons):
    print(f"--- LD {i} ---")
    print(ld[:500])

# Check RSC
next_f_chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)', html, re.DOTALL)
full_rsc = ""
for chunk in next_f_chunks:
    try:
        full_rsc += json.loads('"' + chunk + '"')
    except Exception:
        full_rsc += chunk

print(f"Ashmoret RSC length: {len(full_rsc)}")

# Let's search for any phones or numbers or keys in full_rsc
for key in ['phone', 'tel:', '03-', '08-', '04-', '02-', '09-', '07', '1800', '*']:
    matches = [m.start() for m in re.finditer(re.escape(key), full_rsc)]
    print(f"Matches for {key}: {len(matches)}")
    if matches:
        first = matches[0]
        print(f"  Snippet at {first}: {full_rsc[max(0, first-50):min(len(full_rsc), first+150)]}")

