from __future__ import annotations


def build_signal(context: dict, decision: dict) -> dict:
    bias = context.get("market_bias", "neutral")
    action = decision.get("action", "WATCH")

    if action == "WATCH":
        side = "WATCH"
        confidence = 0.52
    elif bias == "bullish":
        side = "LONG_PAPER"
        confidence = 0.61
    elif bias == "bearish":
        side = "SHORT_PAPER"
        confidence = 0.59
    else:
        side = "WATCH"
        confidence = 0.5

    return {
        "side": side,
        "confidence": confidence,
        "reason": "Research decision requires conditional confirmation." if side == "WATCH" else "Directional paper signal generated.",
    }
