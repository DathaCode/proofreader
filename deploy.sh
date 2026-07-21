#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — deploy/update the Sinhala Proofreader on Ubuntu.
#  Run from the repo root:  ./deploy.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# Always operate from the repo root (where this script lives).
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

COMPOSE="docker compose -f webapp/docker-compose.yml"
DATA_DIR="webapp/data"
BRANCH="prodlotus"

echo "==> Sinhala Proofreader deploy  ($REPO_DIR)"

# 1) Docker installed and running?
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not on PATH." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running (or this user lacks access)." >&2
  echo "       Try: sudo systemctl start docker   (and add your user to the 'docker' group)" >&2
  exit 1
fi
echo "==> Docker OK"

# 2) Ensure the data directory exists with sane permissions.
if [ ! -d "$DATA_DIR" ]; then
  echo "==> Creating $DATA_DIR"
  mkdir -p "$DATA_DIR"
fi
chmod 755 "$DATA_DIR"
echo "==> Data dir ready: $DATA_DIR"

# 3) One-time reconcile: older deploys left web_config.py as an UNTRACKED file.
#    If it's untracked, back it up and remove it so `git pull` can bring the
#    tracked version without an "untracked file would be overwritten" error.
if [ -f webapp/web_config.py ] && ! git ls-files --error-unmatch webapp/web_config.py >/dev/null 2>&1; then
  echo "==> Reconciling untracked webapp/web_config.py (backup -> .local.bak)"
  cp webapp/web_config.py webapp/web_config.py.local.bak
  rm -f webapp/web_config.py
fi

# 4) Pull latest. Handle detached HEAD gracefully.
if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1 && \
   [ "$(git rev-parse --abbrev-ref HEAD)" != "HEAD" ]; then
  echo "==> git pull origin $BRANCH"
  git pull --ff-only origin "$BRANCH" || {
    echo "WARN: fast-forward pull failed; leaving working tree as-is." >&2
  }
else
  echo "==> Detached HEAD detected — checking out $BRANCH first"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH" || true
fi

# 5) Build + start.
echo "==> $COMPOSE up -d --build"
$COMPOSE up -d --build

# 6) Show what's running.
sleep 5
$COMPOSE ps

echo ""
echo "Deployment complete — check http://localhost"
