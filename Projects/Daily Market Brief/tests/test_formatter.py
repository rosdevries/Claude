from src.formatter import format_brief

SAMPLE_HEADLINES = [
    {
        "headline": f"Macro Headline {i}",
        "summary": f"Macro significance sentence one for headline {i}. Sentence two.",
        "source": f"Source {i}",
        "url": f"https://example.com/{i}",
        "published_at": "2026-04-29T10:00:00Z",
    }
    for i in range(1, 6)
]

SAMPLE_PICKS = [
    {
        "ticker": f"TKR{i}",
        "company": f"Company {i}",
        "current_price": f"${100 + i * 10}",
        "catalyst_type": ["earnings", "news", "analyst", "macro", "other"][i % 5],
        "reasoning": f"Reasoning for pick {i}. Second sentence. Third sentence here.",
    }
    for i in range(1, 6)
]

DATE = "2026-04-29"
SAMPLE_TLDR = "Markets traded cautiously today as investors weighed fresh tariff data against solid earnings."


def test_returns_two_strings():
    result = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    assert isinstance(result, tuple) and len(result) == 2
    md, html = result
    assert isinstance(md, str)
    assert isinstance(html, str)


def test_markdown_contains_date():
    md, _ = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    assert DATE in md


def test_markdown_contains_headlines():
    md, _ = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    for h in SAMPLE_HEADLINES:
        assert h["headline"] in md


def test_markdown_contains_tickers():
    md, _ = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    for p in SAMPLE_PICKS:
        assert p["ticker"] in md


def test_html_has_disclaimer():
    _, html = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    assert "Not investment advice" in html


def test_markdown_has_sections():
    md, _ = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    assert "## Top 5 Macro Headlines" in md
    assert "## Top 5 Stock Picks" in md


def test_html_contains_catalyst_types():
    _, html = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    for p in SAMPLE_PICKS:
        assert p["catalyst_type"] in html


def test_html_contains_tickers():
    _, html = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS)
    for p in SAMPLE_PICKS:
        assert p["ticker"] in html


def test_tldr_appears_in_markdown():
    md, _ = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS, SAMPLE_TLDR)
    assert "## TL;DR" in md
    assert SAMPLE_TLDR in md


def test_tldr_appears_in_html():
    _, html = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS, SAMPLE_TLDR)
    assert "TL;DR" in html
    assert SAMPLE_TLDR in html


def test_no_tldr_section_when_empty():
    md, html = format_brief(DATE, SAMPLE_HEADLINES, SAMPLE_PICKS, "")
    assert "## TL;DR" not in md
    assert "TL;DR" not in html
