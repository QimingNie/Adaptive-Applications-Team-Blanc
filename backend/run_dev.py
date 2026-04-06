"""
Run the API with auto-reload on Windows without multiprocessing spawn errors.

Usage (from this folder):
  python run_dev.py

Avoid: `uvicorn app.main:app --reload` via the uvicorn.exe shim on some setups.
"""

from __future__ import annotations

import multiprocessing


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8010,
        reload=True,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
