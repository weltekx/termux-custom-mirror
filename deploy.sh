#!/usr/bin/env bash
# One-shot: create the mirror repo, enable GitHub Pages from main/root,
# import the signing key, build a signed dists/ tree, push. Requires an
# authenticated `gh` CLI and (when signing locally) the secret in the env.
# Usage: ./deploy.sh <github-owner>
set -euo pipefail

OWNER="${1:?usage: ./deploy.sh <github-owner>}"
REPO="termux-custom-mirror"

echo "==> Creating public repo github.com/$OWNER/$REPO"
gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push

if [ -n "${MIRROR_GPG_KEY_B64:-}" ]; then
    echo "==> Importing signing key"
    mkdir -p "$HOME/.gnupg" && chmod 700 "$HOME/.gnupg"
    echo "$MIRROR_GPG_KEY_B64" | base64 -d > "$HOME/.gnupg/key.asc"
    gpg --batch --import "$HOME/.gnupg/key.asc"
fi

echo "==> Building signed mirror (in CI this also runs on every push)"
export GNUPGHOME="${GNUPGHOME:-$HOME/.gnupg}"
python3 scripts/build_mirror.py --root .

echo "==> Committing dists/, pool/, key/ (Pages serves from main, root)"
git add dists pool key curated
git diff --cached --quiet || git commit -m "Initial signed mirror"

echo "==> Enabling GitHub Pages (deploy from main branch, /)"
gh api --method POST "repos/$OWNER/$REPO/pages" --input - <<JSON
{"source": {"branch": "main", "path": "/"}}
JSON

echo "==> Pushing"
git push

echo "==> Done. Mirror is live at:"
echo "    https://$OWNER.github.io/$REPO/"