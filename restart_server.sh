#!/bin/bash
# Restart the development server cleanly

echo "Killing old restart_server.sh processes..."
for pid in $(pgrep -f "restart_server.sh" | grep -v $$); do
    kill -9 $pid 2>/dev/null || true
done
sleep 1

echo "Killing zombie uvicorn processes..."
pkill -9 -f "uvicorn app.main:app" 2>/dev/null
sleep 1

echo "Stopping any existing servers on port 7008..."
lsof -ti:7008 | xargs -r kill -9 2>/dev/null
sleep 1

echo "Verifying port 7008 is free..."
if lsof -ti:7008 >/dev/null 2>&1; then
    echo "ERROR: Port 7008 still in use after cleanup"
    exit 1
fi

echo "Starting server on port 7008..."
cd /mnt/Projects/quantum-pools
source venv/bin/activate
uvicorn app.main:app --reload --port 7008 --host 0.0.0.0
