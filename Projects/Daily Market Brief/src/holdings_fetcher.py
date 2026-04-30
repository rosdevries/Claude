import os
import requests


def fetch_holdings() -> dict:
    url = os.environ.get("DOLLARYDOO_URL", "https://dollarydoo.up.railway.app")
    password = os.environ["DOLLARYDOO_PASSWORD"]
    auth = ("", password)

    summary_resp = requests.get(f"{url}/api/portfolio/summary", auth=auth, timeout=15)
    summary_resp.raise_for_status()
    holdings_resp = requests.get(f"{url}/api/portfolio/holdings", auth=auth, timeout=15)
    holdings_resp.raise_for_status()

    return {"summary": summary_resp.json(), "holdings": holdings_resp.json()}
