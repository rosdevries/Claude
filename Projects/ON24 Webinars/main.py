"""
ON24 Webinar Fetcher
Retrieves webinars tagged 'Lunch & Learn' or 'Customer Expert Series' from client 48920.

Usage:
  python main.py          # terminal table output
  python main.py --html   # HTML output (for email via GitHub Actions)
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests

# Force UTF-8 output on Windows to handle special characters in event titles
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

TOKEN_KEY = os.getenv("ON24_TOKEN_KEY")
TOKEN_SECRET = os.getenv("ON24_TOKEN_SECRET")

BASE_URL = "https://api.on24.com"
EVENT_CLIENT_ID = 48920
TARGET_TAGS = {"Lunch & Learn", "Customer Expert Series"}
LOOKAHEAD_DAYS = 180      # ON24 max date range is 6 months
ONDEMAND_LOOKBACK_DAYS = 30


def auth_headers():
    return {
        "accessTokenKey": TOKEN_KEY,
        "accessTokenSecret": TOKEN_SECRET,
        "accept": "application/json",
    }


def api_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=auth_headers(), params=params)
    r.raise_for_status()
    return r.json()


def fetch_events_paginated(client_id, extra_params):
    """Fetches all pages of events for a client with given filter params."""
    params = {
        "itemsPerPage": 100,
        "pageOffset": 0,
        **extra_params,
    }
    all_events = []
    while True:
        data = api_get(f"/v2/client/{client_id}/event", params=params)
        page = data.get("events", [])
        all_events.extend(page)
        total = data.get("totalevents", 0)
        if len(all_events) >= total or len(page) < params["itemsPerPage"]:
            break
        params["pageOffset"] += 1
    return all_events


def parse_date(raw):
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def format_date(raw):
    dt = parse_date(raw)
    if not dt:
        return raw or "Unknown"
    return dt.strftime("%Y-%m-%d %H:%M UTC%z").replace("+0000", "+00:00")


def build_row(event, matching_tags):
    return {
        "eventid": event.get("eventid"),
        "title": event.get("description") or "Untitled",
        "audienceurl": event.get("audienceurl", ""),
        "livestart": format_date(event.get("livestart")),
        "archiveend": format_date(event.get("archiveend")),
        "tags": sorted(matching_tags),
    }


def collect_events():
    """Fetches and classifies events from client 48920."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    future = (now + timedelta(days=LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")
    lookback = (now - timedelta(days=ONDEMAND_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    seen_ids = set()
    all_events = []

    for extra in [
        # Upcoming: livestart between today and 6 months out
        {"dateFilterMode": "livestart", "startDate": today, "endDate": future},
        # On-demand candidates: livestart in the past 30 days
        {"dateFilterMode": "livestart", "startDate": lookback, "endDate": today},
    ]:
        for e in fetch_events_paginated(EVENT_CLIENT_ID, extra):
            eid = e.get("eventid")
            if eid not in seen_ids:
                seen_ids.add(eid)
                all_events.append(e)

    ondemand_cutoff = now - timedelta(days=ONDEMAND_LOOKBACK_DAYS)
    upcoming, ondemand = [], []
    for event in all_events:
        if event.get("istestevent"):
            continue
        event_tags = set(event.get("tags", []))
        matching = event_tags & TARGET_TAGS
        if not matching:
            continue
        live_dt = parse_date(event.get("livestart"))
        archive_end_dt = parse_date(event.get("archiveend"))
        if live_dt and live_dt > now:
            upcoming.append(build_row(event, matching))
        elif archive_end_dt and archive_end_dt > now and live_dt and live_dt > ondemand_cutoff:
            ondemand.append(build_row(event, matching))

    upcoming.sort(key=lambda e: e["livestart"])
    ondemand.sort(key=lambda e: e["livestart"])
    return upcoming, ondemand


# ── Terminal output ────────────────────────────────────────────────────────────

def print_section(title, rows, date_label, date_key):
    print(f"\n{'='*160}")
    print(f"  {title}  ({len(rows)})")
    print(f"{'='*160}")
    if not rows:
        print("  (none)")
        return
    print(f"  {'Event ID':<12} {date_label:<32} {'Tags':<28} Title")
    print(f"  {'-'*156}")
    for w in rows:
        tags_str = ", ".join(w["tags"])
        print(f"  {str(w['eventid']):<12} {w[date_key]:<32} {tags_str:<28} {w['title']}")


# ── HTML output (for email) ────────────────────────────────────────────────────

def _table_html(section_title, rows, date_label, date_key, header_color, link_titles=False):
    if rows:
        body_rows = ""
        for i, w in enumerate(rows):
            bg = "#ffffff" if i % 2 == 0 else "#f5f7fa"
            tags_str = ", ".join(w["tags"])
            url = w.get("audienceurl", "")
            if link_titles and url:
                title_cell = (
                    f'<a href="{url}" style="color:{header_color};text-decoration:none;font-weight:500">'
                    f'{w["title"]}</a>'
                )
            else:
                title_cell = w["title"]
            body_rows += (
                f'<tr style="background:{bg}">'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0">{w["eventid"]}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;white-space:nowrap">{w[date_key]}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0">{tags_str}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0">{title_cell}</td>'
                f'</tr>'
            )
    else:
        body_rows = '<tr><td colspan="4" style="padding:12px;color:#888;font-style:italic">None</td></tr>'

    return (
        f'<h2 style="color:{header_color};margin-top:32px;margin-bottom:8px">'
        f'{section_title} ({len(rows)})</h2>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px">'
        f'<thead><tr style="background:{header_color};color:#fff">'
        f'<th style="padding:10px 12px;text-align:left">Event ID</th>'
        f'<th style="padding:10px 12px;text-align:left">{date_label}</th>'
        f'<th style="padding:10px 12px;text-align:left">Tags</th>'
        f'<th style="padding:10px 12px;text-align:left">Title</th>'
        f'</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        f'</table>'
    )


def render_html(upcoming, ondemand):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tags_display = " | ".join(sorted(TARGET_TAGS))
    upcoming_html = _table_html("Upcoming Live", upcoming, "Live Start", "livestart", "#1a6b3c", link_titles=True)
    ondemand_html = _table_html(
        f"On Demand (last {ONDEMAND_LOOKBACK_DAYS} days)", ondemand, "Live Date", "livestart", "#1a4b8c"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>ON24 Webinar Report</title></head>"
        "<body style='font-family:Arial,sans-serif;max-width:1100px;margin:0 auto;padding:20px;color:#333'>"
        f"<h1 style='color:#009999;border-bottom:2px solid #009999;padding-bottom:8px'>"
        f"ON24 Webinar Report &mdash; {now_str}</h1>"
        f"<p style='color:#666;margin-top:4px'>Tags: <strong>{tags_display}</strong></p>"
        f"{upcoming_html}{ondemand_html}"
        "<p style='margin-top:40px;font-size:12px;color:#aaa'>Generated automatically from ON24 client 48920</p>"
        "</body></html>"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not all([TOKEN_KEY, TOKEN_SECRET]):
        print("Error: set ON24_TOKEN_KEY and ON24_TOKEN_SECRET in .env", file=sys.stderr)
        sys.exit(1)

    html_mode = "--html" in sys.argv

    try:
        upcoming, ondemand = collect_events()
    except requests.HTTPError as e:
        print(f"API error: {e}\n{e.response.text[:300]}", file=sys.stderr)
        sys.exit(1)

    if html_mode:
        print(render_html(upcoming, ondemand))
        return

    target_list = " | ".join(sorted(TARGET_TAGS))
    print(f"\nFiltering by tags: {target_list}")
    print_section("UPCOMING LIVE", upcoming, "Live Start", "livestart")
    print_section(f"ON DEMAND (last {ONDEMAND_LOOKBACK_DAYS} days)", ondemand, "Live Date", "livestart")
    print()


if __name__ == "__main__":
    main()
