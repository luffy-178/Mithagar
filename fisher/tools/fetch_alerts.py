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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

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


def parse_time(text):
    """RSS (RFC 822) or CAP (ISO 8601) time to an aware datetime, or None."""
    text = (text or "").strip()
    if not text:
        return None
    for fn in (datetime.fromisoformat, parsedate_to_datetime):
        try:
            d = fn(text)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def cap_details(xml_text):
    """Expiry, severity, event and area from one CAP message."""
    root = ET.fromstring(xml_text)
    d = {}
    for el in root.iter():
        k = local(el.tag)
        if k in ("expires", "severity", "event", "areadesc", "effective", "onset") and k not in d and (el.text or "").strip():
            d[k] = el.text.strip()
    return d


def add_validity(alerts, now):
    """Mark each alert active or not. Uses the CAP expiry time; without it, alerts count for 24 hours."""
    looked = 0
    for a in alerts:
        pub = parse_time(a["published"])
        a["active"] = False
        if pub is None or now - pub > timedelta(days=6):
            continue
        exp = None
        if a["link"] and looked < 20:
            looked += 1
            try:
                d = cap_details(fetch(a["link"]))
                a["severity"] = d.get("severity", "")
                a["event"] = d.get("event", "")
                a["area"] = d.get("areadesc", "")[:300]
                a["expires"] = d.get("expires", "")
                exp = parse_time(a["expires"])
            except Exception:
                pass
        a["active"] = (exp > now) if exp else (now - pub < timedelta(hours=24))


def main(path):
    result = {"checked": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": False, "source": "", "error": "", "alerts": []}
    errors = []
    for url, goa_only in FEEDS:
        try:
            result["alerts"] = parse(fetch(url), goa_only)
            add_validity(result["alerts"], datetime.now(timezone.utc))
            result["alerts"] = [a for a in result["alerts"] if a["active"]]
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
