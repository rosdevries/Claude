import logging
import os
import smtplib
import socket
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

log = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


def send_email(date: str, html: str, plaintext: str, subject: str = None) -> None:
    """Try direct SMTP first; fall back to GitHub Actions workflow dispatch."""
    smtp_err = None
    try:
        _send_smtp(date, html, plaintext, subject)
        return
    except Exception as e:
        smtp_err = e
        log.warning("SMTP failed (%s: %s) — falling back to GitHub Actions", type(e).__name__, e)

    _send_via_github_actions(date, smtp_err)


def _send_smtp(date: str, html: str, plaintext: str, subject: str = None) -> None:
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to_addr = os.environ["EMAIL_TO"]
    if subject is None:
        subject = f"Daily Market Brief — {date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.attach(MIMEText(plaintext, "plain"))
    msg.attach(MIMEText(html, "html"))

    # Force IPv4 to avoid EAFNOSUPPORT on hosts without IPv6.
    ipv4 = next(
        addr[4][0]
        for addr in socket.getaddrinfo("smtp.gmail.com", 465, socket.AF_INET, socket.SOCK_STREAM)
    )
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(ipv4, 465, context=context, timeout=15) as server:
        server.login(user, password)
        server.sendmail(user, to_addr, msg.as_string())


def _send_via_github_actions(date: str, smtp_err: Exception) -> None:
    """Trigger the send-email GitHub Actions workflow and wait for it to succeed."""
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]
    workflow_id = "send-email.yml"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Trigger workflow_dispatch
    dispatch_url = f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow_id}/dispatches"
    resp = requests.post(
        dispatch_url,
        headers=headers,
        json={"ref": "main", "inputs": {"date": date}},
        timeout=30,
    )
    resp.raise_for_status()

    # Poll for the workflow run to appear and complete (up to ~5 minutes)
    run_url = f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow_id}/runs"
    run_id = None
    for _ in range(20):
        time.sleep(10)
        runs = requests.get(run_url, headers=headers, params={"per_page": 5}, timeout=30).json()
        for run in runs.get("workflow_runs", []):
            if run.get("head_branch") == "main" and run.get("status") in ("queued", "in_progress", "completed"):
                run_id = run["id"]
                break
        if run_id:
            break

    if not run_id:
        raise RuntimeError(f"SMTP failed ({smtp_err}); GitHub Actions workflow run not found")

    # Wait for completion
    run_detail_url = f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}"
    for _ in range(30):
        time.sleep(10)
        run = requests.get(run_detail_url, headers=headers, timeout=30).json()
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status == "completed":
            if conclusion == "success":
                return
            raise RuntimeError(f"GitHub Actions email workflow finished with conclusion: {conclusion}")

    raise RuntimeError("GitHub Actions email workflow did not complete within timeout")
