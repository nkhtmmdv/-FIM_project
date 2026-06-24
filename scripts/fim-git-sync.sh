#!/usr/bin/env bash
# Sync local repo with GitHub (discard accidental local edits).
set -euo pipefail

BRANCH="${1:-main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[fim] Not a git repository"
    exit 1
fi

echo "[fim] Fetching origin/${BRANCH}..."
git fetch origin "${BRANCH}"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[fim] Local changes detected — resetting to origin/${BRANCH}"
fi

git reset --hard "origin/${BRANCH}"
git clean -fd
