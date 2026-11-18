"""Collect official alerts for Goa from the NDMA SACHET feed and write alerts.json.

SACHET republishes alerts from IMD, INCOIS and the state authority. The feed cannot be
read from a browser, so a scheduled GitHub Action runs this and the app reads the result.
If the feed cannot be reached, ok is false and the app says it could not check.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FEEDS = [
    ("https://sachet.ndma.gov.in/cap_public_website/rss/rss_goa.xml", False),    # state feed
    ("https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml", True),   # national feed, filtered to Goa
]
MARINE = re.compile(r"wave|swell|surge|sea\b|fisher|squall|wind|cyclon|depression|tsunami|current|thunder|lightning|storm|port signal", re.I)


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse(xml_text, goa_only):
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        f = {}
        for child in item:
            k = local(child.tag)
            f[k] = (child.text or child.get("href") or "").strip()
        title = f.get("title", "")
        text = " ".join([title, f.get("description", ""), f.get("summary", "")])
        if goa_only and "goa" not in text.lower():
            continue
        out.append({
            "title": title[:400],
            "agency": f.get("author", "") or f.get("creator", ""),
            "published": f.get("pubdate", "") or f.get("updated", "") or f.get("published", ""),
            "link": f.get("link", ""),
            "marine": bool(MARINE.search(text)),
        })
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fisher-assistant alert check)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def main(path):
    result = {"checked": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": False, "source": "", "error": "", "alerts": []}
    errors = []
    for url, goa_only in FEEDS:
        try:
            result["alerts"] = parse(fetch(url), goa_only)
            result["ok"] = True
            result["source"] = url
            break
        except Exception as e:  # try the next feed
            errors.append(f"{url}: {e}")
    if not result["ok"]:
        result["error"] = " | ".join(errors)[:500]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: result[k] for k in ("checked", "ok", "source", "error")}), "alerts:", len(result["alerts"]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "alerts.json")
