from __future__ import annotations

from typing import Any, Dict, List

from config.settings import env_float
from knowledge_engine.wiki_writer import markdown_doc, wiki_path, write_markdown


def run_scenario_builder(market_context: Dict[str, Any]) -> Dict[str, Any]:
    trigger = env_float("FALLBACK_TRIGGER_PRICE", 107500.0)
    invalidation = env_float("FALLBACK_INVALIDATION_PRICE", 106200.0)
    take_profit = env_float("FALLBACK_TAKE_PROFIT", 110000.0)
    timestamp = str(market_context.get("timestamp_utc", "unknown"))
    current_price = market_context.get("current_price")

    squeeze = markdown_doc("BTC Short Squeeze Scenario", {
        "Status": "active",
        "Direction": "bullish",
        "Core Thesis": (
            "If BTC holds above key support while derivatives positioning remains elevated, "
            "a reclaim above trigger can force shorts to cover."
        ),
        "Current Context": f"Current price: {current_price}. Setup levels are strategy fallbacks unless a dynamic setup engine overrides them.",
        "Conditions": f"- BTC holds above {invalidation}\n- BTC reclaims {trigger}\n- OI remains elevated\n- Funding does not overheat\n- Spot CVD improves",
        "Invalidation": f"- BTC trades below {invalidation}\n- OI drops sharply with price\n- Spot CVD remains negative\n- Exchange inflow increases",
        "Trading Implication": f"Create conditional long watch. Trigger: {trigger}, invalidation: {invalidation}, take profit: {take_profit}.",
        "Related Concepts": "- [[concept/open_interest]]\n- [[concept/funding_rate]]\n- [[concept/cvd]]\n- [[concept/liquidation_heatmap]]",
        "Related Entities": "- [[entity/BTC]]",
        "Confidence": "medium",
        "Last Updated": timestamp,
    })

    breakdown = markdown_doc("BTC Breakdown Scenario", {
        "Status": "watch",
        "Direction": "bearish",
        "Core Thesis": "If BTC fails to hold key support and derivatives unwind accelerates, downside continuation risk increases.",
        "Current Context": f"Current price: {current_price}.",
        "Conditions": f"- BTC loses {invalidation}\n- OI falls with price\n- Spot CVD remains weak\n- Liquidation cluster below price is targeted",
        "Invalidation": f"- BTC reclaims {trigger}\n- Spot CVD turns positive\n- Funding normalizes without price weakness",
        "Trading Implication": "Do not enter long watch if support fails. Wait for new scenario confirmation.",
        "Related Concepts": "- [[concept/open_interest]]\n- [[concept/cvd]]\n- [[concept/liquidation_heatmap]]",
        "Related Entities": "- [[entity/BTC]]",
        "Confidence": "low",
        "Last Updated": timestamp,
    })

    files: List[str] = []
    files.append(str(write_markdown(wiki_path("scenario", "btc_short_squeeze_scenario.md"), squeeze)))
    files.append(str(write_markdown(wiki_path("scenario", "btc_breakdown_scenario.md"), breakdown)))
    return {"status": "SCENARIOS_UPDATED", "files": files}
