from pathlib import Path
import sys
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))
from crypto_ai_system.execution.real_order_test_operator_run_package import persist_p68_real_order_test_operator_run_package
if __name__ == "__main__":
    print(persist_p68_real_order_test_operator_run_package(Path.cwd())["status"])
