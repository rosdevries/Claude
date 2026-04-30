import os

_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
if _provider == "gemini":
    from src.gemini_client import call as _call
else:
    from src.claude_client import call as _call

SYSTEM = """You are a macro market analyst. Identify the top 5 news items most likely to move broad markets or sectors today.

INCLUDE:
- Central bank decisions, rate path signals, Fed/ECB/BOJ speakers, inflation prints (CPI/PPI/PCE), jobs/payroll data
- Geopolitical events affecting commodities, shipping lanes, or trade flows
- Oil/gas, metals, agricultural commodity moves with identifiable supply/demand drivers
- Cross-asset signals: USD strength/weakness, Treasury yield curve moves, credit spread widening, VIX spikes
- Regulatory or fiscal policy at a sector level: tariffs, tax changes, antitrust rulings, major spending bills
- Secular theme datapoints that move them: AI capex announcements, energy transition milestones, supply chain shifts, demographic data
- Large-cap company news ONLY when it functions as a macro proxy (e.g., NVDA capex guidance as a signal for AI infrastructure spending)

EXCLUDE:
- Single-company earnings beats or misses
- Individual stock price moves
- Analyst rating changes or price target updates
- M&A unless it is sector-defining (e.g., a deal that reshapes an entire industry)
- Company-specific news that carries no broader market signal

Use web search to find today's top macro stories from the last 24 hours. Return ONLY a JSON array of exactly 5 items.

Each item must have exactly these fields:
  "headline": string
  "summary": string (2-3 sentences on the macro significance — why it matters for broad markets)
  "source": string (publication name)
  "url": string (article URL)
  "published_at": string (ISO-8601 timestamp)

Return ONLY the JSON array. No prose, no markdown fences, nothing else."""

PROMPT = (
    "Search for today's top 5 macro market stories — central bank signals, "
    "geopolitics, commodities, cross-asset moves, fiscal/regulatory policy, "
    "secular theme datapoints. Exclude single-company earnings and stock moves. "
    "Return ONLY a JSON array."
)


def fetch_macro_headlines() -> list:
    return _call(SYSTEM, PROMPT)
