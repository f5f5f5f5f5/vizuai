"""Legacy Telegram bot entrypoint."""
from __future__ import annotations

import asyncio

from main import run_polling


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
