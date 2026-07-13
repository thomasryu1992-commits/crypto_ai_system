from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Streamlit is intentionally imported only in the UI layer.
# The dashboard generation logic stays testable without Streamlit installed.
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_ai_system.ops.operator_dashboard_status import (  # noqa: E402
    SAFE_REVIEW_ONLY_SCRIPTS,
    build_operator_dashboard_status,
    persist_operator_dashboard_status,
)

st.set_page_config(page_title="Crypto_AI_System Operator Console", layout="wide")


FORBIDDEN_NOTICE = """
This console is read-only. It does not submit orders, enable testnet/live execution,
accept API secrets/private keys, mutate settings, or enable executors.
"""


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - UI rendering branch
        return {"error": str(exc), "path": str(path)}
    return data if isinstance(data, dict) else {"value": data}


def render_kv(data: Dict[str, Any], keys: list[str]) -> None:
    rows = []
    for key in keys:
        rows.append({"field": key, "value": data.get(key)})
    st.table(rows)


def run_review_only_script(label: str, script_rel_path: str) -> None:
    script = ROOT / script_rel_path
    if script_rel_path not in SAFE_REVIEW_ONLY_SCRIPTS.values():
        st.error("Blocked: script is not in the review-only allowlist.")
        return
    if not script.exists():
        st.error(f"Missing script: {script_rel_path}")
        return
    result = subprocess.run(  # nosec B603 - allowlisted local review-only scripts only
        [sys.executable, str(script)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        st.success(f"Review-only script completed: {label}")
        if result.stdout:
            st.code(result.stdout)
    else:
        st.error(f"Review-only script failed: {label}")
        st.code(result.stderr or result.stdout)


def main() -> None:
    st.title("Crypto_AI_System Operator Console")
    st.caption("Review-only / signed-testnet-preparation status dashboard")
    st.warning(FORBIDDEN_NOTICE)

    latest_dir = ROOT / "storage" / "latest"

    with st.sidebar:
        st.header("Review-only actions")
        st.write("These actions only regenerate reports. They cannot submit orders or enable execution.")
        if st.button("Refresh dashboard status", type="primary"):
            persist_operator_dashboard_status(ROOT)
            st.success("operator_dashboard_status.json regenerated")
        st.divider()
        for label, script_rel_path in SAFE_REVIEW_ONLY_SCRIPTS.items():
            if label == "Operator dashboard status":
                continue
            if st.button(f"Generate: {label}"):
                run_review_only_script(label, script_rel_path)
        st.divider()
        st.subheader("Disabled controls")
        st.write("Order submit: Disabled")
        st.write("Testnet/live enable: Disabled")
        st.write("Executor enable: Disabled")
        st.write("Settings mutation: Disabled")
        st.write("Secret/private key input: Disabled")

    status = load_json(latest_dir / "operator_dashboard_status.json")
    if status is None:
        status = persist_operator_dashboard_status(ROOT)
    else:
        # Rebuild in memory so UI reflects any newly generated reports while preserving file if desired.
        status = build_operator_dashboard_status(ROOT)

    tabs = st.tabs([
        "System Status",
        "Data Health",
        "ResearchSignal",
        "RiskGate",
        "Approval & Blockers",
        "Reports",
    ])

    with tabs[0]:
        st.subheader("System Status")
        col1, col2, col3 = st.columns(3)
        col1.metric("Stage", status["project_stage"])
        col2.metric("Execution flags disabled", str(status["execution_flags_all_disabled"]))
        col3.metric("Frontend authority", status["frontend_authority"])
        if status["unsafe_true_execution_flags"]:
            st.error("Unsafe true flags detected")
            st.json(status["unsafe_true_execution_flags"])
        else:
            st.success("All tracked execution/order/runtime mutation flags are disabled.")
        st.subheader("Execution Flags")
        st.json(status["execution_flags"])
        st.subheader("Disabled Controls")
        st.json(status["disabled_controls"])

    with tabs[1]:
        st.subheader("Data Health")
        st.json(status["data_health"])
        st.subheader("Data reports")
        st.json(status["reports"].get("data_health", {}))

    with tabs[2]:
        st.subheader("ResearchSignal")
        st.json(status["research_signal"])
        st.subheader("ResearchSignal reports")
        st.json(status["reports"].get("research_signal", {}))

    with tabs[3]:
        st.subheader("PreOrderRiskGate / Hot-path Risk")
        st.json(status["risk_gate"])
        st.subheader("Risk reports")
        st.json(status["reports"].get("risk_gate", {}))

    with tabs[4]:
        st.subheader("Approval & Remaining Blockers")
        st.metric("Blocker count", status["approval_and_blockers"]["blocker_count"])
        st.json(status["approval_and_blockers"])
        st.subheader("Safe next actions")
        for action in status["safe_next_actions"]:
            st.write(f"- {action}")

    with tabs[5]:
        st.subheader("Recent JSON Reports")
        st.dataframe(status["reports"].get("recent_json_reports", []), use_container_width=True)
        st.subheader("Recent Markdown Reports")
        st.dataframe(status["reports"].get("recent_markdown_reports", []), use_container_width=True)
        st.subheader("Raw dashboard status")
        st.json(status)


if __name__ == "__main__":
    main()
