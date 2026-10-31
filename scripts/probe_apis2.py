import json

import httpx

h = httpx.get("https://himalayas.app/jobs/api?limit=1", timeout=25, headers={"User-Agent": "Mozilla/5.0"})
job = h.json()["jobs"][0]
print("HIMALAYAS KEYS", list(job.keys()))
print({k: job[k] for k in job if k not in ("description", "excerpt")})

a = httpx.get("https://www.arbeitnow.com/api/job-board-api", timeout=25, headers={"User-Agent": "Mozilla/5.0"})
print("ARBEITNOW", a.status_code, a.json().keys())
item = a.json()["data"][0]
print("ARBEITNOW KEYS", list(item.keys()))
print({k: item[k] for k in item if k != "description"})

for ua in ("EuroJobsPro/2.0 (+contact@example.com)", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"):
    m = httpx.get("https://www.themuse.com/api/public/jobs?page=1", timeout=25,
                  headers={"User-Agent": ua, "Accept": "application/json"})
    print("MUSE", m.status_code, m.text[:150])

r = httpx.get("https://api.reliefweb.int/v1/jobs?appname=eurojobspro&profile=list&limit=1", timeout=25)
print("RW", r.status_code, r.text[:300])
