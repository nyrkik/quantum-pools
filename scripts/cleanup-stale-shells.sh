#!/bin/bash
# Cleanup stale background processes
# Run manually or add to crontab: */30 * * * * ~/quantum-pools/scripts/cleanup-stale-shells.sh

# Kill npm run dev processes older than 3 hours
pkill -f "npm run dev" -u $USER --older-than 3h 2>/dev/null

# Kill restart_server.sh processes older than 1 hour
pkill -f "restart_server.sh" -u $USER --older-than 1h 2>/dev/null

# Log cleanup
echo "[$(date)] Cleanup completed" >> /tmp/quantum-pools-cleanup.log
