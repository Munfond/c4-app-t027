"""Run from the repo: python -m scripts.experiment_worker --once (or continuous polling)."""

import argparse
import logging
import time

from src.services import sensor_studies
from src.services.experiment_runner import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        if not args.once:
            sensor_studies.advance_running()
        result = run_once()
        if result:
            print(f"{result['id']} {result['status']}", flush=True)
        if args.once:
            if result and result["status"] == "failed":
                raise SystemExit(1)
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
