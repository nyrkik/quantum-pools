#!/usr/bin/env python3
"""EMD Scraper — single run. Called by systemd timer."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.emd_daily_scraper import run_daily_scrape

if __name__ == "__main__":
    asyncio.run(run_daily_scrape())
