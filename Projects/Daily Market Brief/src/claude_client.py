import json
import os
import time
import anthropic

from src.response_parser import parse_json_list

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}

HEADLINES_SYSTEM = (
    "You are a financial news researcher. Your job is to find the top 10 "
    "US-relevant financial and market headlines from the last 24 hours.\n\n"
    "IMPORTANT: Use the web_search tool to find current news. After searching, "
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
    "IMPORTANT: Use web_search. Return ONLY a JSON array.\n\n"
    "Each item must have exactly these fields:\n"
    '  "ticker": string\n'
    '  "company": string\n'
    '  "current_price": string\n'
    '  "catalyst_type": string (one of: earnings/news/analyst/macro/other)\n'
    '  "reasoning": string (2-3 sentences)\n\n'
    "Exactly 5 items, US-listed, catalysts from last 24-48 hours, no evergreen picks. "
    "Return ONLY the JSON array."
)


def _run_to_completion(system_text: str, user_prompt: str):
    messages = [{"role": "user", "content": user_prompt}]
    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    for _ in range(5):
        response = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            return response
        if response.stop_reason == "pause_turn":
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response.content},
            ]
            continue
        return response
    return response


def _parse_json_response(response) -> list:
    text_content = None
    for block in response.content:
        if block.type == "text":
            text_content = block.text
    if text_content is None:
        raise ValueError("No text block found in API response")
    return parse_json_list(text_content)


def _call_with_retry(system_text: str, user_prompt: str, max_retries: int = 3) -> list:
    last_exc = None
    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(2 ** attempt)
        try:
            result = _run_to_completion(system_text, user_prompt)
            return _parse_json_response(result)
        except (json.JSONDecodeError, ValueError, anthropic.APIError) as e:
            last_exc = e
    raise RuntimeError(f"All {max_retries} attempts failed: {last_exc}") from last_exc


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
    response = _client.messages.create(
        model=MODEL,
        max_tokens=512,
        system="You are a concise financial editor. Write plain prose only.",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
