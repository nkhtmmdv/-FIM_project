#!/usr/bin/env bash
# FIM Sentinel — full update script
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "==> Syncing code from GitHub..."
bash scripts/fim-git-sync.sh main

echo "==> Rebuilding images..."
docker compose build --pull

echo "==> Recreating all containers with new config..."
docker compose up -d --force-recreate

chmod +x scripts/fim-start.sh scripts/fim-open-dashboard.sh scripts/fim-git-sync.sh 2>/dev/null || true

echo ""
echo "✅ Done! FIM Sentinel updated and running."
echo "   → Dashboard: http://localhost:8080"
echo ""
echo "   To refresh autostart settings: sudo bash install.sh"
echo ""
echo "   After updating, go to Settings → Baseline Management"
echo "   and click 'Create New Baseline' to start fresh monitoring."
