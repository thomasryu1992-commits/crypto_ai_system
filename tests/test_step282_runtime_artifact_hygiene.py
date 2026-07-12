from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.build_audit_bundle import build_audit_bundle
from scripts.build_source_package import build_source_package


def test_step282_source_package_excludes_runtime_outputs(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    for rel in ["storage/latest/a.json", "data/reports/r.json", "data/stores/s.json", "dist/old.zip"]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime", encoding="utf-8")

    output = tmp_path / "source.zip"
    build_source_package(root, output)

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())

    assert "crypto_ai_system_source/src/app.py" in names
    assert not any("/storage/" in name for name in names)
    assert not any("/data/reports/" in name for name in names)
    assert not any("/data/stores/" in name for name in names)
    assert not any("/dist/" in name for name in names)


def test_step282_validation_bundle_may_include_runtime_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for rel in ["storage/latest/research_signal.json", "storage/logs/event_log.jsonl", "data/reports/report.json", "data/stores/store.json"]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (root / "README.md").write_text("readme", encoding="utf-8")

    output = tmp_path / "validation.zip"
    build_audit_bundle(root, output)

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())

    assert "crypto_ai_system_validation/storage/latest/research_signal.json" in names
    assert "crypto_ai_system_validation/storage/logs/event_log.jsonl" in names
    assert "crypto_ai_system_validation/data/reports/report.json" in names
    assert "crypto_ai_system_validation/data/stores/store.json" in names
