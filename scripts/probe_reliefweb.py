import httpx

for url in [
    "https://api.reliefweb.int/v1/jobs?appname=workatlas&profile=list&limit=1",
    "https://api.reliefweb.int/v1/jobs?appname=workatlas&limit=1",
    "https://reliefweb.int/jobs/rss.xml",
    "https://reliefweb.int/jobs/rss.xml?search=volunteer",
]:
    try:
        r = httpx.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        print(url, r.status_code, r.headers.get("content-type"), r.text[:300].replace("\n", " "))
    except Exception as e:
        print(url, "ERR", e)
