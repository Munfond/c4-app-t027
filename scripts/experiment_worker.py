"""Run from the repo: python -m scripts.experiment_worker --once (or continuous polling)."""

import argparse
import logging
import time
from contextlib import nullcontext

from src.services.experiment_runner import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        from src.services import experiment_sessions as sessions
        from src.services import experiment_store as store
        from src.services.sensor_studies import advance_running

        sessions.sweep()
        result = None
        for root in [None, *sessions.active()]:
            if root is not None:
                try:
                    sessions.acquire(root.name, renew=False)
                except KeyError:
                    continue  # The tab may have ended this session after enumeration.
            try:
                with store.scope(root) if root is not None else nullcontext():
                    advance_running()
                    result = run_once()
                    advance_running()
            finally:
                if root is not None:
                    sessions.release(root.name)
            if result:
                break
        sessions.sweep()
        if result:
            print(f"{result['id']} {result['status']}", flush=True)
        if args.once:
            if result and result["status"] == "failed":
                raise SystemExit(1)
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
