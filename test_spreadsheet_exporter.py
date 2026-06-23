from __future__ import annotations

from integrations.spreadsheet_exporter import export_latest_results, export_latest_results_to_csv


def test_export_latest_results_to_csv() -> None:
    result = export_latest_results_to_csv()
    assert result["status"] == "EXPORTED_LOCAL_CSV"


def test_export_latest_results() -> None:
    result = export_latest_results()
    assert result["status"] == "EXPORTED"
    assert "local_csv" in result
    assert "google_sheets" in result


if __name__ == "__main__":
    test_export_latest_results_to_csv()
    test_export_latest_results()
    print("PASSED")
