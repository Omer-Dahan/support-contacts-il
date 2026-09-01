import requests
import json
import re

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://sherutplus.com/bezeq', headers=headers)
html = r.text

next_f_chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)', html, re.DOTALL)
full_rsc = ''
for chunk in next_f_chunks:
    try:
        full_rsc += json.loads('"' + chunk + '"')
    except Exception:
        full_rsc += chunk

m = re.search(r'\"aiSummaryText\":\s*\"\$([^\"]+)\"', full_rsc)
if m:
    ref_id = m.group(1)
    print('Found ref_id:', ref_id)
    m2 = re.search(re.escape(ref_id) + r':T([0-9a-fA-F]+),', full_rsc)
    print('Found chunk match:', m2)
    if m2:
        clen = int(m2.group(1), 16)
        text = full_rsc[m2.end():m2.end()+clen]
        clean_text = text.split('window.addEventListener')[0].split('<script')[0].strip()
        print('Extracted clean AI summary:')
        print(clean_text)
