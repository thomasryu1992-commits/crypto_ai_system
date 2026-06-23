from __future__ import annotations

from typing import Any, Dict

from knowledge_engine.wiki_writer import markdown_doc, wiki_path, write_markdown


def run_entity_builder(market_context: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(market_context.get("symbol") or "BTCUSDT")
    current_price = market_context.get("current_price")
    content = markdown_doc("BTC", {
        "Type": "Asset",
        "Current Thesis": "BTC remains the primary market beta asset. Short-term direction is influenced by liquidity, derivatives positioning, spot confirmation, and macro risk sentiment.",
        "Key Metrics": f"- Symbol: {symbol}\n- Current Price: {current_price}\n- Open Interest\n- Funding Rate\n- Spot CVD\n- Liquidation Levels",
        "Related Concepts": "- [[concept/open_interest]]\n- [[concept/funding_rate]]\n- [[concept/cvd]]\n- [[concept/liquidation_heatmap]]",
        "Related Scenarios": "- [[scenario/btc_short_squeeze_scenario]]\n- [[scenario/btc_breakdown_scenario]]",
        "Last Updated": str(market_context.get("timestamp_utc", "unknown")),
    })
    path = write_markdown(wiki_path("entity", "BTC.md"), content)
    return {"status": "ENTITY_UPDATED", "files": [str(path)]}
