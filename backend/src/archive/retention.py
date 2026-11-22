import argparse
from datetime import datetime, timedelta, timezone
from src.archive.store import ArchiveStore
from src.config import Settings
from src.db import make_engine

def main():
    parser = argparse.ArgumentParser(description="Archive retention; dry run by default")
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 3650:
        parser.error("days must be between 1 and 3650")
    engine = make_engine(Settings())
    try:
        count = ArchiveStore(engine).retention(datetime.now(timezone.utc)-timedelta(days=args.days),apply=args.apply)
        print(f"{'deleted' if args.apply else 'eligible'}: {count}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    main()
