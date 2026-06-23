from __future__ import annotations

from typing import Any, Dict, List

from knowledge_engine.wiki_writer import markdown_doc, wiki_path, write_markdown

CONCEPTS = {
    "open_interest": {
        "title": "Open Interest",
        "definition": "Open Interest represents the total value of outstanding derivative contracts that have not been settled.",
        "bullish": "- Price up + OI up: trend continuation possible\n- Price up + OI down: short covering possible",
        "bearish": "- Price down + OI up: short buildup or trapped longs\n- Price down + OI down: long liquidation or position unwind",
        "risk": "OI alone is not directional. Interpret it with price, funding, CVD, and liquidation levels.",
    },
    "funding_rate": {
        "title": "Funding Rate",
        "definition": "Funding rate reflects the cost paid between long and short perpetual futures traders.",
        "bullish": "Neutral or negative funding during price strength can imply under-positioned longs or trapped shorts.",
        "bearish": "Excessively positive funding can imply crowded longs and liquidation risk.",
        "risk": "Funding must be compared against OI, basis, spot flow, and liquidation clusters.",
    },
    "cvd": {
        "title": "CVD",
        "definition": "Cumulative Volume Delta tracks aggressive buyer versus seller activity.",
        "bullish": "Rising spot CVD can confirm real demand behind price strength.",
        "bearish": "Falling spot CVD during price rebound can imply weak demand or perp-led move.",
        "risk": "Exchange-specific CVD can diverge and should not be used alone.",
    },
    "liquidation_heatmap": {
        "title": "Liquidation Heatmap",
        "definition": "Liquidation heatmap estimates price zones where leveraged positions may be forced to close.",
        "bullish": "Large liquidation clusters above price can create short squeeze magnets.",
        "bearish": "Large clusters below price can create downside liquidity sweeps.",
        "risk": "Liquidation maps are estimates, not guaranteed targets.",
    },
}


def run_concept_builder(market_context: Dict[str, Any]) -> Dict[str, Any]:
    files: List[str] = []
    for slug, data in CONCEPTS.items():
        content = markdown_doc(data["title"], {
            "Definition": data["definition"],
            "Bullish Interpretation": data["bullish"],
            "Bearish Interpretation": data["bearish"],
            "Risk": data["risk"],
            "Related Entities": "- [[entity/BTC]]",
            "Related Scenarios": "- [[scenario/btc_short_squeeze_scenario]]\n- [[scenario/btc_breakdown_scenario]]",
            "Last Updated": str(market_context.get("timestamp_utc", "unknown")),
        })
        path = write_markdown(wiki_path("concept", f"{slug}.md"), content)
        files.append(str(path))
    return {"status": "CONCEPTS_UPDATED", "files": files}
