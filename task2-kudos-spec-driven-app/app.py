#!/usr/bin/env python3
"""Entry point for running the Datacom Kudos Portal locally."""

import logging
import os

from server import KudosHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> None:
    host = os.environ.get("KUDOS_HOST", "127.0.0.1")
    port = int(os.environ.get("KUDOS_PORT", "8000"))
    db_path = os.environ.get(
        "KUDOS_DB_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "kudos.db"),
    )

    httpd = KudosHTTPServer((host, port), db_path=db_path, seed_demo_data=True)
    logger.info("Datacom Kudos Portal running at http://%s:%d (DB: %s)", host, port, db_path)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
