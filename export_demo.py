"""Export the offline browser bundle to frontend/public/data.

    python scripts/export_demo.py               binary bundle (any static host)
    python scripts/export_demo.py --text_assets  also convert frontend/dist/data
                                                 compressed files to base64 text,
                                                 for hosts that only serve text
                                                 and web media types
"""
import argparse
import base64
from pathlib import Path

from vigilix.export.bundle import export


def text_assets(folder: Path) -> None:
    for f in sorted(folder.glob("*.gz")):
        (folder / (f.name + ".b64.txt")).write_text(base64.b64encode(f.read_bytes()).decode())
        f.unlink()
        print("  converted", f.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text_assets", action="store_true", help="convert frontend/dist/data after make web")
    args = ap.parse_args()
    if args.text_assets:
        text_assets(Path(__file__).resolve().parents[1] / "frontend" / "dist" / "data")
    else:
        export()
