import json
import re


def parse_json_list(text: str) -> list:
    text = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*\n([\s\S]*?)\n```\s*$', text, re.MULTILINE)
    if fence_match:
        text = fence_match.group(1).strip()
    if not text.startswith("["):
        arr_match = re.search(r'\[[\s\S]*\]', text)
        if arr_match:
            text = arr_match.group(0)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    return data
