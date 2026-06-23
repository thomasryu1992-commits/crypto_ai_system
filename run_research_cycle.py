from core.console import configure_utf8_console, safe_print
from research.research_cycle import run_research_cycle

configure_utf8_console()


def main() -> dict:
    result = run_research_cycle()
    safe_print("[RESEARCH CYCLE]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Research Score: {result.get('research_score')}")
    return result


if __name__ == "__main__":
    main()
