import json

import httpx

urls = {
    "jobicy": "https://jobicy.com/api/v2/remote-jobs?count=2",
    "remotive": "https://remotive.com/api/remote-jobs?limit=2",
    "remoteok": "https://remoteok.com/api",
    "himalayas": "https://himalayas.app/jobs/api?limit=2",
    "themuse": "https://www.themuse.com/api/public/jobs?page=1",
    "reliefweb": "https://api.reliefweb.int/v1/jobs?appname=eurojobspro-test&profile=list&limit=2",
}
for name, url in urls.items():
    try:
        r = httpx.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        print("==", name, r.status_code, r.headers.get("content-type"), len(r.content))
        try:
            d = r.json()
            if isinstance(d, list):
                print("list len", len(d))
                item = d[1] if name == "remoteok" and len(d) > 1 else d[0]
                print(json.dumps(item, ensure_ascii=False)[:1200])
            else:
                print("keys", list(d.keys())[:12])
                for k in ("data", "jobs", "results", "items"):
                    if k in d and isinstance(d[k], list) and d[k]:
                        print("sample", json.dumps(d[k][0], ensure_ascii=False)[:1500])
                        break
        except Exception as e:
            print("json err", e, r.text[:200])
    except Exception as e:
        print("==", name, "ERR", e)
