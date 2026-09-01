import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

for path in ['bezeq', 'legal/bezeq', 'reviews/bezeq', 'cancel/bezeq', 'solutions/bezeq', 'branches/bezeq']:
    url = f'https://sherutplus.com/{path}'
    r = requests.get(url, headers=headers, timeout=15)
    print(f"URL: {url} -> status {r.status_code}, len {len(r.text)}")

