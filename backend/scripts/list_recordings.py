"""List the recordings in storage, newest last, and optionally download one to listen to.

Run from backend/:
    uv run python -m scripts.list_recordings
    uv run python -m scripts.list_recordings sessions/7/abc.wav     # saves abc.wav here
"""

import argparse
from pathlib import Path

from app.api.deps import get_audio_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="List or download stored recordings.")
    parser.add_argument("key", nargs="?", help="key of a recording to download")
    args = parser.parse_args()

    storage = get_audio_storage()
    if args.key:
        target = Path(args.key).name
        storage.client.download_file(storage.bucket, args.key, target)
        print(f"Saved {target}")
        return

    objects = storage.client.list_objects_v2(Bucket=storage.bucket).get("Contents", [])
    for obj in sorted(objects, key=lambda o: o["LastModified"]):
        print(f"{obj['LastModified']:%Y-%m-%d %H:%M}  {obj['Size'] / 1024:8.1f} KB  {obj['Key']}")
    print(f"{len(objects)} recording(s) in {storage.bucket}")


if __name__ == "__main__":
    main()
