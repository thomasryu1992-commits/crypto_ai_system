from core.console import configure_utf8_console, safe_print
from research.research_decision import make_research_decision

configure_utf8_console()


def main() -> dict:
    result = make_research_decision()
    safe_print("[RESEARCH DECISION]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Decision Type: {result.get('decision_type')}")
    return result


if __name__ == "__main__":
    main()
