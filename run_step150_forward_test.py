from __future__ import annotations

import argparse

from forward_test.paper_forward_runner import run_forward_test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=7)
    args = parser.parse_args()
    result = run_forward_test(iterations=args.iterations)
    print(f"Step150 forward test runner: {result['status']} completed={result['completed_iterations']}")


if __name__ == "__main__":
    main()
