"""
WSGI entry point for production deployment with Waitress.

This module provides a production WSGI server entry point for the broll web UI.
It uses Waitress, a pure-Python WSGI server that's ideal for Raspberry Pi deployments.

Environment Variables:
    BROLL_DRIVE_PATH: Path to the external drive (required)
    BROLL_HOST: Host to bind to (default: 0.0.0.0)
    BROLL_PORT: Port to listen on (default: 5555)
    BROLL_THREADS: Number of worker threads (default: 4)

Usage:
    BROLL_DRIVE_PATH=/path/to/drive python -m broll.web.wsgi
    waitress-serve --port=5555 --host=0.0.0.0 broll.web.wsgi:application
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from waitress import serve

from .app import create_app


def get_application():
    """Create and return the Flask application instance for WSGI servers."""
    drive_path = os.environ.get("BROLL_DRIVE_PATH")

    if not drive_path:
        # For use with waitress-serve CLI, drive path must be set via env
        print(
            "ERROR: BROLL_DRIVE_PATH environment variable is required",
            file=sys.stderr,
        )
        print(
            "Example: BROLL_DRIVE_PATH=/media/openclaw/Crucial\\ X10 waitress-serve ...",
            file=sys.stderr,
        )
        sys.exit(1)

    drive = Path(drive_path)
    if not drive.exists():
        # Don't fail here - let the app's check_drive_connected() handle it
        # This allows the server to start even if drive is temporarily disconnected
        print(f"WARNING: Drive path does not exist: {drive}", file=sys.stderr)
        print("Server will start, but requests will show 'drive not connected'", file=sys.stderr)

    return create_app(str(drive))


# WSGI application instance
# Used by: waitress-serve broll.web.wsgi:application
application = get_application()


def main():
    """Run the Waitress server with configuration from environment."""
    host = os.environ.get("BROLL_HOST", "0.0.0.0")
    port = int(os.environ.get("BROLL_PORT", "5555"))
    threads = int(os.environ.get("BROLL_THREADS", "4"))

    # Get the application instance
    app = application

    print(f"Starting broll-catalog server on {host}:{port}")
    print(f"Drive path: {os.environ.get('BROLL_DRIVE_PATH', 'NOT SET')}")
    print(f"Threads: {threads}")

    serve(
        app,
        host=host,
        port=port,
        threads=threads,
        ident="broll-catalog",
        _quiet=False,
    )


if __name__ == "__main__":
    main()
