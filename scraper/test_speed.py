import time
import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
}

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=1)
session.mount('https://', adapter)
session.headers.update(headers)

test_urls = [
    'https://sherutplus.com/bezeq',
    'https://sherutplus.com/klal',
    'https://sherutplus.com/menora',
    'https://sherutplus.com/home-center',
    'https://sherutplus.com/ikea',
    'https://sherutplus.com/ashmoret',
    'https://sherutplus.com/hot',
    'https://sherutplus.com/shufersal',
    'https://sherutplus.com/el-al',
    'https://sherutplus.com/wizz-air',
    'https://sherutplus.com/max',
    'https://sherutplus.com/maccabi',
    'https://sherutplus.com/clalit',
    'https://sherutplus.com/electra',
    'https://sherutplus.com/super-pharm',
    'https://sherutplus.com/paz',
    'https://sherutplus.com/cellcom',
    'https://sherutplus.com/partner',
    'https://sherutplus.com/yes',
    'https://sherutplus.com/pelephone'
]

def fetch_one(url):
    t0 = time.time()
    try:
        r = session.get(url, timeout=30)
        dt = time.time() - t0
        return url, r.status_code, len(r.content), dt, None
    except Exception as e:
        dt = time.time() - t0
        return url, 0, 0, dt, str(e)

t_start = time.time()
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(fetch_one, u) for u in test_urls]
    for f in as_completed(futures):
        url, code, length, dt, err = f.result()
        print(f"[{code}] {url} -> {length} bytes in {dt:.2f}s (err: {err})")

total_time = time.time() - t_start
print(f"Total time for {len(test_urls)} requests with 4 workers: {total_time:.2f}s ({len(test_urls)/total_time:.2f} req/s)")
