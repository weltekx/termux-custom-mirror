#!/usr/bin/env bash
# One-shot: create the mirror repo, enable GitHub Pages via Actions, push,
# and trigger the index build. Requires an authenticated `gh` CLI.
# Usage: ./deploy.sh <github-owner>
set -euo pipefail

OWNER="${1:?usage: ./deploy.sh <github-owner>}"
REPO="termux-custom-mirror"

echo "==> Creating public repo github.com/$OWNER/$REPO"
gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push

echo "==> Enabling GitHub Pages (Actions source)"
gh api --method POST "repos/$OWNER/$REPO/pages" --input - <<JSON
{"build_type": "workflow"}
JSON

echo "==> Triggering the mirror build"
gh workflow run generate-pages.yml --repo "$OWNER/$REPO"

echo "==> Done. Mirror builds at:"
echo "    https://$OWNER.github.io/$REPO/"
echo "    Watch progress: gh run watch --repo $OWNER/$REPO"