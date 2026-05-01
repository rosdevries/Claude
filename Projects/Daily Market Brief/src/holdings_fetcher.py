import os
import requests


def fetch_holdings() -> dict:
    url = os.environ.get("DOLLARYDOO_URL", "https://dollarydoo.up.railway.app")
    password = os.environ["DOLLARYDOO_PASSWORD"].strip()
    headers = {"X-Api-Key": password}

    try:
        summary_resp = requests.get(f"{url}/api/portfolio/summary", headers=headers, timeout=15)
        summary_resp.raise_for_status()
        holdings_resp = requests.get(f"{url}/api/portfolio/holdings", headers=headers, timeout=15)
        holdings_resp.raise_for_status()
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        raise RuntimeError(f"DollarYDoo {e.response.status_code}: {body}") from e

    return {"summary": summary_resp.json(), "holdings": holdings_resp.json()}
