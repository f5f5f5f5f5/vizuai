"""Background worker entrypoint."""
from __future__ import annotations

import asyncio

from main import run_worker


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
