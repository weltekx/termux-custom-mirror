# termux-custom-mirror

Custom APT repository for the LinuxDictApp practice terminal, hosted on
GitHub Pages.

When the workflow runs, it renders the package manifest (`catalog.json`)
into an APT-compatible layout:

    dists/stable/main/binary-aarch64/Packages
    dists/stable/main/binary-arm/Packages
    dists/stable/main/binary-x86_64/Packages
    dists/stable/main/binary-x86/Packages

The app points its `sources.list` at

    deb https://<owner>.github.io/termux-custom-mirror/ stable main

and `pkg update` inside the terminal fetches the ABI-specific `Packages`
index. If the mirror is unreachable the app falls back to its bundled
offline catalog.

## Keeping the manifest in sync

`catalog.json` mirrors the package list in the app's
`PkgManager.kt` (`data/PkgManager.kt`). Regenerate it from the app sources:

    python3 scripts/sync_catalog.py <path-to-app>/app/src/main/java/com/weltekxdev/linuxdict/app/data/PkgManager.kt

Commit the updated `catalog.json`; the workflow rebuilds the indexes and
re-deploys automatically on push to `main`.

## One-shot deploy

From an authenticated `gh` CLI:

    ./deploy.sh <owner>

This creates the public repository, enables Pages (Actions source), pushes,
and triggers the workflow. The mirror is live at
`https://<owner>.github.io/termux-custom-mirror/` once the workflow finishes.