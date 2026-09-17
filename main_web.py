"""FastAPI web API entrypoint."""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("WEB_API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("WEB_API_PORT", "8080")))
    uvicorn.run("web_api.app:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
