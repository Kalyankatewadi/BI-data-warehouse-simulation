"""
Build the BI data warehouse end to end.

    python build_warehouse.py --sample     # synthetic fixtures, no downloads
    python build_warehouse.py              # real source data

Stages: extract -> transform -> load -> validate. Validation failure aborts the
build, so a database that finishes building is a database that passed its checks.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config
import extract
import transform
import load
import validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the BI data warehouse")
    parser.add_argument("--sample", action="store_true",
                        help="use synthetic fixtures instead of real sources")
    args = parser.parse_args()

    started = time.time()
    log.info("=" * 62)
    log.info("BI DATA WAREHOUSE BUILD")
    log.info("=" * 62)

    try:
        log.info("[1/4] Extract")
        raw = extract.extract_all(use_sample=args.sample)

        log.info("[2/4] Transform")
        tables = transform.transform_all(raw)

        log.info("[3/4] Load")
        loaded = load.build(tables)

        log.info("[4/4] Validate")
        validate.run_all()

    except transform.ExcessiveDropError as exc:
        log.error("Build aborted: %s", exc)
        return 1
    except validate.ValidationError as exc:
        log.error("Build aborted: %s", exc)
        return 1
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1

    elapsed = time.time() - started
    total = sum(loaded.values())
    log.info("=" * 62)
    log.info("BUILD COMPLETE in %.1fs", elapsed)
    log.info("Database: %s", config.DB_PATH)
    log.info("Total rows loaded: %s", f"{total:,}")
    for name, count in loaded.items():
        log.info("    %-16s %s", name, f"{count:,}")
    log.info("=" * 62)
    log.info("These are the numbers to put in your README.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
