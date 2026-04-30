import logging
import os
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv

load_dotenv()

_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
if _provider == "gemini":
    from src.gemini_client import fetch_stock_picks, fetch_tldr
else:
    from src.claude_client import fetch_stock_picks, fetch_tldr

from src.macro_brief import fetch_macro_headlines

from src.emailer import send_email
from src.formatter import format_brief
from src.github_store import commit_summary
from src.holdings_fetcher import fetch_holdings

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def main():
    pt = pytz.timezone("America/Los_Angeles")
    today = datetime.now(pt).strftime("%Y-%m-%d")
    log.info("Starting daily brief for %s", today)

    try:
        headlines = fetch_macro_headlines()
        log.info("Fetched %d macro headlines", len(headlines))
    except Exception as e:
        log.error("Macro headlines failed: %s", e)
        _fail_email(today, "macro headlines", str(e))
        sys.exit(1)

    try:
        picks = fetch_stock_picks()
        log.info("Fetched %d stock picks", len(picks))
    except Exception as e:
        log.error("Stock picks failed: %s", e)
        _fail_email(today, "stock picks", str(e))
        sys.exit(1)

    try:
        tldr = fetch_tldr(headlines, picks)
        log.info("TLDR generated")
    except Exception as e:
        log.warning("TLDR failed (non-fatal): %s", e)
        tldr = ""

    try:
        portfolio = fetch_holdings()
        log.info("Portfolio fetched (%d holdings)", len(portfolio.get("holdings", [])))
    except Exception as e:
        log.warning("Portfolio fetch failed (non-fatal): %s", e)
        portfolio = None

    markdown, html = format_brief(today, headlines, picks, tldr, portfolio)

    try:
        commit_summary(today, markdown, html)
        log.info("GitHub commit succeeded")
    except Exception as e:
        log.warning("GitHub commit failed (non-fatal): %s", e)

    for attempt in range(1, 3):
        try:
            send_email(today, html, markdown)
            log.info("Email sent")
            break
        except Exception as e:
            if attempt == 1:
                log.warning("Email attempt 1 failed: %s — retrying", e)
            else:
                log.error("Email failed after retry: %s", e)

    log.info("Done.")


def _fail_email(date: str, step: str, error: str) -> None:
    try:
        send_email(
            date,
            f"<p>Daily Market Brief failed at step: <b>{step}</b></p><pre>{error}</pre>",
            f"Daily Market Brief failed at step: {step}\n\n{error}",
            subject=f"Daily Brief FAILED — {date}",
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
