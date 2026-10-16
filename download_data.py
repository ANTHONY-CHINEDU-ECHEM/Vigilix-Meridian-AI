"""Download every public source with checksums (resumable). Usage: python scripts/download_data.py"""
from vigilix.data.acquire import acquire_all

if __name__ == "__main__":
    acquire_all()
