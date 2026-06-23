from __future__ import annotations

from typing import Any, Dict

from knowledge_engine.wiki_writer import markdown_doc, wiki_path, write_markdown


def run_source_builder(market_context: Dict[str, Any]) -> Dict[str, Any]:
    content = markdown_doc("Coinalyze", {
        "Type": "Derivatives data provider",
        "Used Metrics": "- Open Interest\n- Funding Rate\n- Long/Short Ratio\n- Liquidation Data",
        "Reliability": "- Category: market data\n- Latency risk: medium\n- Manipulation risk: low",
        "Related Concepts": "- [[concept/open_interest]]\n- [[concept/funding_rate]]\n- [[concept/liquidation_heatmap]]",
        "Last Updated": str(market_context.get("timestamp_utc", "unknown")),
    })
    path = write_markdown(wiki_path("source", "coinalyze.md"), content)
    return {"status": "SOURCE_UPDATED", "files": [str(path)]}
