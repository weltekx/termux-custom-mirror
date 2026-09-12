#!/usr/bin/env bash
# One-shot: create the mirror repo, enable GitHub Pages from main/root,
# push, and commit a freshly generated index. Requires an authenticated
# `gh` CLI. Usage: ./deploy.sh <github-owner>
set -euo pipefail

OWNER="${1:?usage: ./deploy.sh <github-owner>}"
REPO="termux-custom-mirror"

echo "==> Creating public repo github.com/$OWNER/$REPO"
gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push

echo "==> Generating index"
python3 scripts/generate_index.py

echo "==> Committing dists/ (Pages serves from main, root)"
git add dists
git diff --cached --quiet || git commit -m "Initial mirror index"

echo "==> Enabling GitHub Pages (deploy from main branch, /)"
gh api --method POST "repos/$OWNER/$REPO/pages" --input - <<JSON
{"source": {"branch": "main", "path": "/"}}
JSON

echo "==> Pushing"
git push

echo "==> Done. Mirror is live at:"
echo "    https://$OWNER.github.io/$REPO/"