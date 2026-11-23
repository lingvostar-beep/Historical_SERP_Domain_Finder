"""CLI: python -m app.worker.cli --run-id <uuid>"""

from __future__ import annotations

import argparse
import json
import uuid

from app.worker.serp_worker import process_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a SERP run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-queries", type=int, default=None)
    args = parser.parse_args()
    result = process_run(uuid.UUID(args.run_id), max_queries=args.max_queries)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
