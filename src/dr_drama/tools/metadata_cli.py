"""Interactive metadata preview; saving requires an explicit confirmation."""

import argparse
import json
from pathlib import Path

from dr_drama.data.watch_history import STATUSES, save_metadata
from dr_drama.tools.mydramalist import MetadataError, MyDramaListClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", nargs="?")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/watch_history.csv"))
    args = parser.parse_args()
    client = None
    try:
        title = args.title or input("Drama title: ").strip()
        client = MyDramaListClient.from_env(args.env_file)
        candidates = client.search(title)
        if not candidates:
            print("No matches found. Try another title or spelling. Nothing saved.")
            return 0
        for index, candidate in enumerate(candidates, 1):
            print(f"{index}. {candidate['title']} ({candidate['year'] or 'year unknown'}) — {candidate['slug']}")
            print(f"   {candidate['url']}")
        choice = input("Choose a result number (Enter cancels): ").strip()
        if not choice:
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(candidates):
            print("Invalid selection. Nothing saved.")
            return 1
        selected = candidates[int(choice) - 1]
        metadata, raw, warnings = client.fetch(selected['slug'])
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        for warning in warnings:
            print("Note:", warning)
        if input("Confirm the match and save metadata to watch history? [y/N]: ").strip().lower() != "y":
            print("Nothing saved.")
            return 0
        status = input("Status for a NEW row (completed/dropped/unfinished/watching; existing status is preserved): ").strip()
        if status and status not in STATUSES:
            raise ValueError("Invalid status. Nothing saved.")
        save_metadata(args.dataset, title, metadata, status or None)
        # Retain response snapshots separately from the normalized collection ledger.
        snapshot_dir = args.dataset.parent / "api_responses"
        timestamp = metadata['metadata_retrieved_at'].replace(':', '-')
        snapshot = snapshot_dir / f"mdl-{metadata['external_api_id']}-{timestamp}.json"
        try:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot.write_text(json.dumps({"metadata": metadata, "responses": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            print("Metadata saved, but the response snapshot could not be written.")
        print(f"Saved metadata to {args.dataset}; existing personal fields preserved.")
        return 0
    except (MetadataError, ValueError, OSError) as error:
        print(f"Error: {error}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 0
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
