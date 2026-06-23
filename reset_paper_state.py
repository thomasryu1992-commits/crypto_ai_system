from __future__ import annotations

from core.console import configure_utf8_console, safe_print
from core.json_io import write_storage_json


def main() -> None:
    configure_utf8_console()
    state = {"active_position": None, "closed_trades": []}
    write_storage_json("paper_state.json", state)
    safe_print("Paper state reset completed.")


if __name__ == "__main__":
    main()
