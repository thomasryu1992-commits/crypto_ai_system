from core.console import configure_utf8_console, safe_print
from research.dynamic_setup_generator import generate_dynamic_setup

configure_utf8_console()


def main() -> dict:
    result = generate_dynamic_setup()
    safe_print("[DYNAMIC SETUP]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Decision Type: {result.get('decision_type')}")
    return result


if __name__ == "__main__":
    main()
