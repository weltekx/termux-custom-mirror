# termux-custom-mirror

Package metadata mirror for the LinuxDictApp practice terminal, served from
GitHub Pages.

The mirror is **metadata only** — it never contains `.deb` binaries. The app's
`pkg` command is catalog-based: `pkg update` fetches the ABI-specific
`Packages` index and `pkg install` adds the package to the app's installed
set (no apt, no dpkg, no real archive download).

## Layout

GitHub Pages serves this repository directly from the `main` branch (root),
so the generated index tree is committed into `main`:

    dists/stable/main/binary-aarch64/Packages
    dists/stable/main/binary-arm/Packages
    dists/stable/main/binary-x86_64/Packages
    dists/stable/main/binary-x86/Packages

The app fetches

    https://<owner>.github.io/termux-custom-mirror/dists/stable/main/binary-<abi>/Packages

over TLS. There is intentionally no offline fallback in the app: if the
mirror is unreachable, `pkg update` reports a fetch error.

## Keeping the manifest in sync

`catalog.json` mirrors the package list in the app's `PkgManager.kt`
(`data/PkgManager.kt`). Regenerate it from the app sources:

    python3 scripts/sync_catalog.py <path-to-app>/app/src/main/java/com/weltekxdev/linuxdict/app/data/PkgManager.kt

Then commit the updated `catalog.json`. The workflow `generate-pages.yml`
rebuilds `dists/` from it and commits the result back to `main`, where
GitHub Pages picks it up automatically.

## Deploying to a new owner

From an authenticated `gh` CLI, so Pages serves from `main` (root):

    gh repo create <owner>/termux-custom-mirror --public --source=. --remote=origin --push
    gh api --method POST repos/<owner>/termux-custom-mirror/pages --input - <<'JSON'
    {"source": {"branch": "main", "path": "/"}}
    JSON