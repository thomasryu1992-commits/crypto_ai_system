#!/usr/bin/env bash
# Idempotent server setup for the paper pipeline (Ubuntu 22.04/24.04, x86 or ARM).
# Run as the deploy user from the repo root; uses sudo only for systemd install.
#
#   INSTALL_DIR=/opt/crypto_ai_system RUN_USER=$USER bash deploy/setup_server.sh
#
# What it does: venv + deps, one verification cycle, systemd timers
# (pipeline / 15 min, factory / daily). It does NOT touch storage/ - migrate
# or start fresh per docs/DEPLOY_LINUX_SERVER.md, and NEVER run two machines
# against diverging storage histories at once.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"
RUN_USER="${RUN_USER:-$(id -un)}"
cd "$INSTALL_DIR"

echo "== [1/5] python venv =="
PYBIN="$(command -v python3.11 || command -v python3)"
"$PYBIN" -c 'import sys; assert sys.version_info >= (3, 11), f"need >=3.11, got {sys.version}"'
[ -d .venv ] || "$PYBIN" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip

echo "== [2/5] dependencies =="
# x10 (Extended signed SDK) and streamlit are NOT needed by the headless paper
# pipeline; x10 may lack ARM wheels, so fall back to installing without them.
if ! .venv/bin/pip install --quiet -r requirements.txt; then
  echo "full requirements failed (likely x10 on ARM) - installing headless subset"
  grep -vE '^(x10-python-trading-starknet|streamlit)' requirements.txt > /tmp/req_headless.txt
  .venv/bin/pip install --quiet -r /tmp/req_headless.txt
fi

echo "== [3/5] verification (safety guard + one cycle) =="
mkdir -p storage/logs
.venv/bin/python scripts/check_safety_defaults.py
# run_scheduler --once returns 0 iff the cycle was healthy; a clean no-trade
# cycle (pipeline exit 2, P0-6) already counts as healthy inside it.
if PYTHONUTF8=1 .venv/bin/python run_scheduler.py --once; then
  echo "verification cycle OK"
else
  echo "verification cycle FAILED - fix before enabling timers"
  exit 1
fi

echo "== [4/5] systemd units =="
chmod +x deploy/run_factory_once.sh
for unit in crypto-ai-pipeline.service crypto-ai-pipeline.timer crypto-ai-factory.service crypto-ai-factory.timer; do
  sed -e "s|/opt/crypto_ai_system|$INSTALL_DIR|g" -e "s|^User=crypto$|User=$RUN_USER|" \
    "deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" > /dev/null
done
sudo systemctl daemon-reload

echo "== [5/5] enable timers =="
sudo systemctl enable --now crypto-ai-pipeline.timer crypto-ai-factory.timer
systemctl list-timers 'crypto-ai-*' --no-pager

echo
echo "done. tail the pipeline with:  tail -f $INSTALL_DIR/storage/logs/scheduler.log"
echo "REMINDER: disable the Windows scheduled tasks on the old machine (one runner only)."
