#!/usr/bin/env python3
"""Customer Agent Email Poller — runs as systemd service, polls every 60s."""

import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds


async def main():
    from src.services.customer_agent import run_poll_cycle

    logger.info("Customer Agent Poller started")

    while True:
        try:
            count = await run_poll_cycle()
            if count > 0:
                logger.info(f"Processed {count} emails")
        except Exception as e:
            logger.error(f"Poll cycle error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
