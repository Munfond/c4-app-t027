"""Explicit, additive schema initialization; never seeds or deletes Lab/media data."""

from src.services.remote_database import initialize


def main():
    initialize()
    print("Remote queue schema v1 ready. Lab tables were not modified.")


if __name__ == "__main__":
    main()
