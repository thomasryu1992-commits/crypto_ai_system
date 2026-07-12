from __future__ import annotations

from pathlib import Path

from scripts.run_agent_evals import build_agent_eval_report, discover_eval_cases, persist_agent_eval_report
from crypto_ai_system.registry.base_registry import load_registry_records


def test_step324_discovers_required_high_risk_eval_cases() -> None:
    paths = [path.as_posix() for path in discover_eval_cases(Path.cwd())]

    assert any("valid_approval_intake.json" in path for path in paths)
    assert any("missing_required_id.json" in path for path in paths)
    assert any("hash_mismatch.json" in path for path in paths)
    assert any("stale_data.json" in path for path in paths)
    assert any("fallback_synthetic_sample_data.json" in path for path in paths)
    assert any("missing_approval_packet.json" in path for path in paths)
    assert any("damaged_approval_file.json" in path for path in paths)
    assert any("prohibited_runtime_mutation_attempt.json" in path for path in paths)
    assert any("broken_canonical_id_chain.json" in path for path in paths)


def test_step324_agent_eval_report_passes_and_preserves_review_only_safety() -> None:
    report = build_agent_eval_report(Path.cwd())

    assert report["status"] == "AGENT_EVALS_PASSED"
    assert report["passed"] is True
    assert report["review_only"] is True
    assert report["runtime_permission_source"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["eval_case_count"] >= 9
    assert report["blocked_case_count"] >= 8
    assert report["fail_closed_case_count"] >= 8
    assert report["errors"] == []


def test_step324_prohibited_runtime_mutation_eval_fails_closed() -> None:
    report = build_agent_eval_report(Path.cwd())
    record = next(item for item in report["records"] if item["eval_case_id"] == "prohibited_runtime_mutation_attempt")

    assert record["passed"] is True
    assert record["actual_passed"] is False
    assert record["actual_blocked"] is True
    assert record["actual_fail_closed"] is True
    assert "prohibited_runtime_mutation_performed" in record["actual_block_reasons"]


def test_step324_persists_eval_report_and_append_only_registry(tmp_path: Path) -> None:
    root = tmp_path
    source_root = Path.cwd()
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\nstorage:\n  registry_dir: storage/registries\n  latest_dir: storage/latest\n",
        encoding="utf-8",
    )
    src = source_root / "agent_contracts" / "eval_cases"
    dst = root / "agent_contracts" / "eval_cases"
    for path in src.rglob("*.json"):
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    result = persist_agent_eval_report(root)

    assert result["report"]["passed"] is True
    assert (root / "storage" / "latest" / "agent_eval_report.json").exists()
    rows = load_registry_records(root / "storage" / "registries" / "agent_eval_registry.jsonl")
    assert len(rows) == 1
    assert rows[0]["runtime_permission_source"] is False
    assert rows[0]["order_submission_performed"] is False
