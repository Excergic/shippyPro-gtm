"""Original ShippyPro signal-first workflow, with SQLite lead persistence."""
import argparse
import json
from pathlib import Path
from signal_pipeline import build as build_accounts
import outbound_engine
from shippypro_db import sync


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build'])
    parser.add_argument('--campaign', action='store_true', help='Also rebuild the ShippyPro research and message drafts')
    args = parser.parse_args()
    build_accounts()
    campaign = outbound_engine.build() if args.campaign else (outbound_engine.state() if Path(outbound_engine.DB).exists() else None)
    print(json.dumps(sync(campaign), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
