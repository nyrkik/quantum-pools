#!/bin/bash
# Restart the development server cleanly

echo "Stopping any existing servers on port 7007..."
lsof -ti:7007 | xargs -r kill -9 2>/dev/null
sleep 1

echo "Starting server on port 7007..."
cd /mnt/Projects/RouteOptimizer
source venv/bin/activate
uvicorn app.main:app --reload --port 7007 --host 0.0.0.0
