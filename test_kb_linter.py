from __future__ import annotations

from knowledge_engine.kb_linter import run_kb_lint


def main() -> None:
    result = run_kb_lint()
    print("[KB LINTER TEST]")
    print(f"Status: {result.get('status')}")
    print(f"Errors: {result.get('error_count')}")
    print(f"Warnings: {result.get('warning_count')}")


if __name__ == "__main__":
    main()
