import json
import os
import time

from google import genai
from google.genai import types

from src.response_parser import parse_json_list

_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))

MODEL = "gemini-3-flash-preview"
SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

HEADLINES_SYSTEM = (
    "You are a financial news researcher. Your job is to find the top 10 "
    "US-relevant financial and market headlines from the last 24 hours.\n\n"
    "Use Google Search to find current news. After searching, "
    "return ONLY a JSON array — no prose, no explanation, no markdown fences.\n\n"
    "Each array item must have exactly these fields:\n"
    '  "headline": string\n'
    '  "summary": string (1-2 sentence summary)\n'
    '  "source": string (publication name)\n'
    '  "url": string (article URL)\n'
    '  "published_at": string (ISO-8601 timestamp)\n\n'
    "Requirements: Exactly 10 items, last 24 hours only, US-relevant, "
    "deduplicated. Return ONLY the JSON array, nothing else."
)

STOCK_PICKS_SYSTEM = (
    "You are a market analyst. Find the top 5 US stock picks with specific "
    "catalysts from the last 24-48 hours.\n\n"
    "Use Google Search to find current information. Return ONLY a JSON array.\n\n"
    "Each item must have exactly these fields:\n"
    '  "ticker": string\n'
    '  "company": string\n'
    '  "current_price": string\n'
    '  "catalyst_type": string (one of: earnings/news/analyst/macro/other)\n'
    '  "reasoning": string (2-3 sentences)\n\n'
    "Exactly 5 items, US-listed, catalysts from last 24-48 hours, no evergreen picks. "
    "Return ONLY the JSON array."
)


def _run(system: str, prompt: str) -> str:
    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=[SEARCH_TOOL],
        ),
    )
    return response.text


def _call_with_retry(system: str, prompt: str, max_retries: int = 3) -> list:
    last_exc = None
    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(2 ** attempt)
        try:
            text = _run(system, prompt)
            return parse_json_list(text)
        except (json.JSONDecodeError, ValueError, Exception) as e:
            last_exc = e
    raise RuntimeError(f"All {max_retries} attempts failed: {last_exc}") from last_exc


def fetch_headlines() -> list:
    return _call_with_retry(
        HEADLINES_SYSTEM,
        "Search for the top 10 US financial and market headlines from the last 24 hours. "
        "Return ONLY a JSON array.",
    )


def fetch_stock_picks() -> list:
    return _call_with_retry(
        STOCK_PICKS_SYSTEM,
        "Search for the top 5 US stock picks with specific catalysts from the last 24-48 hours. "
        "Return ONLY a JSON array.",
    )


def call(system: str, prompt: str, max_retries: int = 3) -> list:
    return _call_with_retry(system, prompt, max_retries)


def fetch_tldr(headlines: list, picks: list) -> str:
    context = json.dumps({"headlines": headlines, "stock_picks": picks})
    prompt = (
        "Based on the following headlines and stock picks, write a single concise paragraph "
        "(3-5 sentences) that summarises the most important market story of the day, "
        "mentions 1-2 notable stock moves, and conveys the overall market mood. "
        "Plain prose only — no bullet points, no markdown, no headers.\n\n" + context
    )
    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a concise financial editor. Write plain prose only.",
        ),
    )
    return response.text.strip()
