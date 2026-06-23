from __future__ import annotations

from pathlib import Path


def test_knowledge_base_exists() -> None:
    assert Path("knowledge_base").exists()


if __name__ == "__main__":
    test_knowledge_base_exists()
    print("PASSED")
