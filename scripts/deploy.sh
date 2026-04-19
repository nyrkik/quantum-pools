#!/bin/bash
# Deploy script — the ONLY way to deploy changes.
# Restarts all services, verifies they're running, checks for errors.

set -e

echo "=== QuantumPools Deploy ==="

# 0. Event-discipline audit — blocks deploy on NEW drift from taxonomy,
#    canonical paths, PII-in-payload rule, or the agent-learning DNA rule.
#    Pre-existing debt is allowlisted via the baseline; only new
#    regressions fail. See app/scripts/audit_event_discipline.py.
echo "Running event-discipline audit..."
if ! /home/brian/00_MyProjects/QuantumPools/venv/bin/python /srv/quantumpools/app/scripts/audit_event_discipline.py > /tmp/qp_discipline.out 2>&1; then
  echo "FAILED: event-discipline audit found new drift — fix before deploying"
  cat /tmp/qp_discipline.out
  exit 1
fi
tail -5 /tmp/qp_discipline.out

# 1. Build frontend
echo ""
echo "Building frontend..."
cd /srv/quantumpools/frontend
npm run build --silent 2>&1 | tail -3

# 2. Restart ALL services
echo "Restarting all services..."
sudo systemctl restart quantumpools-backend quantumpools-frontend quantumpools-agent

# 3. Wait for startup
sleep 3

# 4. Verify all three are running
FAILED=0
for svc in quantumpools-backend quantumpools-frontend quantumpools-agent; do
  if ! systemctl is-active --quiet "$svc"; then
    echo "FAILED: $svc is not running!"
    sudo journalctl -u "$svc" --since "30 sec ago" --no-pager | tail -5
    FAILED=1
  else
    echo "  ✓ $svc"
  fi
done

# 5. Verify backend responds
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7061/api/v1/auth/me 2>/dev/null)
if [ "$HTTP" = "401" ]; then
  echo "  ✓ backend API responding"
else
  echo "FAILED: backend API returned $HTTP"
  FAILED=1
fi

# 6. Verify frontend responds
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7060 2>/dev/null)
if [ "$HTTP" = "307" ] || [ "$HTTP" = "200" ]; then
  echo "  ✓ frontend responding"
else
  echo "FAILED: frontend returned $HTTP"
  FAILED=1
fi

# 7. Check for immediate 500s in backend logs
ERRORS=$(sudo journalctl -u quantumpools-backend --since "10 sec ago" --no-pager 2>&1 | grep -c "ERROR" || true)
if [ "$ERRORS" -gt 0 ]; then
  echo "WARNING: $ERRORS errors in backend logs"
  sudo journalctl -u quantumpools-backend --since "10 sec ago" --no-pager 2>&1 | grep "ERROR"
fi

# 8. Check agent poller processed without crash
AGENT_ERRORS=$(sudo journalctl -u quantumpools-agent --since "5 sec ago" --no-pager 2>&1 | grep -c "Error\|Exception\|Traceback" || true)
if [ "$AGENT_ERRORS" -gt 0 ]; then
  echo "FAILED: agent poller has errors"
  sudo journalctl -u quantumpools-agent --since "5 sec ago" --no-pager 2>&1 | grep "Error\|Exception" | tail -3
  FAILED=1
fi

if [ "$FAILED" -eq 1 ]; then
  echo ""
  echo "⚠ DEPLOY HAS ISSUES — check above"
  exit 1
else
  echo ""
  echo "Deploy complete — all services verified"
fi
