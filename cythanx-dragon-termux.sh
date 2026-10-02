#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# CYTHANX unattended launcher for Termux. Credentials are environment-only.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${SCRIPT_DIR}/godpunks_converged_miner.py"

if ! command -v python >/dev/null 2>&1; then
  echo "Python is missing. Install it with: pkg install python" >&2
  exit 1
fi

# Safe defaults: no pool configured means local CYTHANX mining, no prompts.
export CYTHANX_POOL_ENABLED="${CYTHANX_POOL_ENABLED:-1}"
export CYTHANX_POOL_PROTOCOL="${CYTHANX_POOL_PROTOCOL:-cythanx}"
export CYTHANX_THREADS="${CYTHANX_THREADS:-$(python -c 'import os; print(max(1, min(4, os.cpu_count() or 1)))')}"
export CYTHANX_KEEPALIVE="${CYTHANX_KEEPALIVE:-1}"

if [[ -z "${CYTHANX_POOL_URL:-}" ]]; then
  echo "No CYTHANX_POOL_URL set: running local CYTHANX mining."
  echo "For a compatible pool, set CYTHANX_POOL_URL, CYTHANX_POOL_USER, and CYTHANX_POOL_PASS first."
else
  echo "Pool endpoint configured: ${CYTHANX_POOL_URL}"
  echo "Protocol: ${CYTHANX_POOL_PROTOCOL}; workers: ${CYTHANX_THREADS}"
fi

exec python "$SCRIPT"
