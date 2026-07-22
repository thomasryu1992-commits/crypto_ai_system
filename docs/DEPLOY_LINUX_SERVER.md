# Deploy: 24/7 paper pipeline on a Linux server

Target: an always-on cloud VM (planned: Oracle Cloud, **Singapore** region)
running the paper pipeline every 15 minutes and the strategy factory daily —
the same two jobs the Windows Task Scheduler runs today, without the gaps
when the desktop is off.

**Scope guard**: this deploys the PAPER pipeline + read-only probes only. No
API keys, no order-capable flags, nothing in `.env` is required on the server.
All live/testnet enablement remains a separate operator action and is NOT part
of this runbook.

## 0. Server sizing / region notes

- 2 vCPU / 2-4 GB RAM is plenty (a cycle is ~20-30s of pandas every 15 min).
  Oracle free-tier ARM (Ampere A1) works — the lean runtime is pure Python
  (`x10-python-trading-starknet` is NOT imported by it; the setup script
  falls back to a headless install if that wheel fails on ARM).
- Singapore region: Binance futures public API is reachable (avoid US regions
  — Binance blocks US IPs). Extended API has no such restriction.
- Ubuntu 22.04 or 24.04, Python >= 3.11 (CI targets 3.11 semantics).
- No inbound ports needed. Keep the default "deny all inbound" security list;
  SSH only.
- Oracle free-tier note: idle free instances can be reclaimed — upgrading the
  account to Pay-As-You-Go (still $0 within free limits) removes that risk.

## 1. Install

```bash
sudo apt update && sudo apt install -y git python3.11 python3.11-venv  # 22.04; 24.04: python3/python3-venv
sudo mkdir -p /opt/crypto_ai_system && sudo chown "$USER" /opt/crypto_ai_system
git clone https://github.com/thomasryu1992-commits/crypto_ai_system.git /opt/crypto_ai_system
cd /opt/crypto_ai_system
INSTALL_DIR=/opt/crypto_ai_system RUN_USER=$USER bash deploy/setup_server.sh
```

The setup script is idempotent: venv + deps, `check_safety_defaults.py`, one
verification cycle via `run_scheduler.py --once` (a clean no-trade cycle —
pipeline exit 2 — already counts as healthy), then installs and enables the
two systemd timers:

| unit | cadence | mirrors |
|---|---|---|
| `crypto-ai-pipeline.timer` | every 15 min | `CryptoAISystemPaperScheduler` |
| `crypto-ai-factory.timer` | daily 20:00 UTC | `CryptoAISystemStrategyFactory` |

## 2. Storage migration — ONE RUNNER ONLY (do not skip)

`storage/` (paper history, registries, basis samples) is gitignored,
machine-local operator data. Two schedulers on two machines produce two
diverging histories — the 2026-07-18 cross-machine merge is not an experience
to repeat.

On the **Windows PC**, in this order:

```powershell
# 1. stop the local runners FIRST
Disable-ScheduledTask -TaskName CryptoAISystemPaperScheduler
Disable-ScheduledTask -TaskName CryptoAISystemStrategyFactory
# 2. then copy the history to the server (run from the repo root)
scp -r storage ubuntu@<server-ip>:/opt/crypto_ai_system/
```

Then enable the timers on the server (setup script already did). To instead
start the server's history from zero, skip the copy and run
`py scripts/reset_paper_outcomes.py --confirm` semantics do not apply — a
fresh clone simply has no history; the risk guard fails closed until the
first outcomes accumulate, which is correct.

Direction of trust: after migration the SERVER owns `storage/`; treat the
Windows copy as a frozen backup.

## 3. Operating it

```bash
systemctl list-timers 'crypto-ai-*'                     # next firings
tail -f /opt/crypto_ai_system/storage/logs/scheduler.log
.venv/bin/python scripts/dashboard.py                   # status board
.venv/bin/python scripts/paper_performance_summary.py   # accumulated stats
journalctl -u crypto-ai-pipeline.service -n 50          # if a unit misfires
```

- Overlap safety: `core/run_lock.py` (fcntl on Linux) makes a slow cycle and
  the next timer firing mutually exclusive — the second run refuses, exit 40.
- `Persistent=true` on both timers: a missed firing (reboot, maintenance)
  runs once at boot instead of silently skipping.
- Console encoding: not an issue on Linux (UTF-8 default); `PYTHONUTF8=1` is
  set in the units anyway.
- Updates: `git pull && .venv/bin/python -m pytest -q` on the server, same
  4-step verification contract as everywhere else (`/verify`).

## 4. Optional: alerting

`TELEGRAM_ENABLED` + bot token env vars wire the existing notifier seam; or a
5-line cron that greps `scheduler.log` for `exit=` values not in {0, 2} and
mails/pings. Not required for correctness — the timers + lock are self-healing.

## 5. What deliberately stays manual

- Any testnet/live key, flag, or confirmation phrase (operator, per STATUS.md
  gates — the server has no secrets by design).
- Re-enabling the Windows tasks (only if decommissioning the server).
- The factory's gates/caps in `deploy/run_factory_once.sh` — keep in sync
  with `scripts/run_factory_once.bat` when either changes.
