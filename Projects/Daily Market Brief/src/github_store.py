import base64
import os
import requests

GITHUB_API = "https://api.github.com"


def _upsert_file(headers: dict, repo: str, path: str, content: str, message: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=headers, timeout=30)
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if resp.status_code == 200:
        payload["sha"] = resp.json()["sha"]
    requests.put(url, headers=headers, json=payload, timeout=30).raise_for_status()


def commit_summary(date: str, markdown: str, html: str = "") -> None:
    local_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "summaries")
    os.makedirs(local_dir, exist_ok=True)
    with open(os.path.join(local_dir, f"{date}.md"), "w", encoding="utf-8") as f:
        f.write(markdown)

    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    _upsert_file(headers, repo, f"summaries/{date}.md", markdown, f"Daily brief: {date}")
    if html:
        _upsert_file(headers, repo, f"summaries/{date}.html", html, f"Daily brief HTML: {date}")
