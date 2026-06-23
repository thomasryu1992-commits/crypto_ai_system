from core.console import configure_utf8_console, safe_print
from collectors.real_market_data_collector import collect_real_market_data

configure_utf8_console()


def main() -> dict:
    result = collect_real_market_data()
    safe_print("[REAL MARKET DATA COLLECTOR]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Provider: {result.get('provider')}")
    safe_print(f"Symbol: {result.get('symbol')}")
    safe_print(f"Interval: {result.get('interval')}")
    safe_print(f"OK Endpoints: {result.get('ok_endpoints')}")
    safe_print(f"Error Endpoints: {result.get('error_endpoints')}")
    return result


if __name__ == "__main__":
    main()
