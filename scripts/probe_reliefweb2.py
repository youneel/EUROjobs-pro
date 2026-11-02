import json

import httpx

for url in [
    "https://api.reliefweb.int/v2/jobs?appname=workatlas&profile=list&limit=2",
    "https://api.reliefweb.int/v2/jobs?appname=workatlas&limit=2&query[value]=volunteer",
]:
    try:
        r = httpx.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        print(url, r.status_code, r.text[:200])
        if r.status_code == 200:
            d = r.json()
            print("keys", list(d.keys()))
            if d.get("data"):
                print(json.dumps(d["data"][0], ensure_ascii=False)[:1800])
    except Exception as e:
        print("ERR", e)
