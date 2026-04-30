import os
import requests


def fetch_holdings() -> dict:
    url = os.environ.get("DOLLARYDOO_URL", "https://dollarydoo.up.railway.app")
    password = os.environ["DOLLARYDOO_PASSWORD"]
    auth = ("", password)

    summary = requests.get(f"{url}/api/portfolio/summary", auth=auth, timeout=15).json()
    holdings = requests.get(f"{url}/api/portfolio/holdings", auth=auth, timeout=15).json()

    return {"summary": summary, "holdings": holdings}
