# termux-custom-mirror

Signed APT package mirror for the LinuxDictApp practice terminal, served from
GitHub Pages — Termux-style: a real `apt` repository with real `.deb`
binaries hosted under `pool/` and a `dists/` tree signed by the project's own
GPG key.

The app configures apt with:

```
deb [signed-by=$PREFIX/etc/apt/linuxdict-keyring.gpg] https://<owner>.github.io/termux-custom-mirror stable main
```

so `pkg install` / `pkg update` are thin wrappers over real `apt-get`.

## Layout

GitHub Pages serves this repository directly from the `main` branch (root),
so the generated tree is committed into `main`:

    dists/stable/InRelease                     # clearsigned Release (our key)
    dists/stable/Release
    dists/stable/main/binary-<abi>/Packages[.gz]
    pool/aarch64/<pkg>_<ver>_<arch>.deb        # real .debs (aarch64)
    key/linuxdict-signing-key.gpg[.asc]        # public signing key
    curated/pool.txt                           # curated packages to host
    curated/installed.txt                      # bootstrap packages (excluded)

Packages in the app catalog that have a hosted `.deb` (plus their transitive
dependencies) get full real fields — `Filename`/`Size`/`SHA256`/etc. The rest
stay metadata-only stanzas, so `apt` reports "no installation candidate" for
them until their `.deb` is added to `curated/pool.txt`.

## Regenerating the mirror

`scripts/build_mirror.py`:

1. fetches Termux's aarch64 package index,
2. resolves dependency closures for `curated/pool.txt` (excluding the
   bootstrap-installed set in `curated/installed.txt`),
3. downloads any missing `.deb`s into `pool/aarch64/`,
4. renders `Packages` + `Packages.gz` for all four ABIs,
5. writes `dists/stable/Release`, signs it into `InRelease` with the project
   key, and verifies with `gpgv`.

It needs a local `GNUPGHOME` containing the signing secret:

    GNUPGHOME=/path/to/gnupg python3 scripts/build_mirror.py --root .

The workflow `generate-pages.yml` runs exactly this on every push (key
imported from the `MIRROR_GPG_KEY_B64` secret) and commits the result back to
`main`, which GitHub Pages serves.

## Keeping the manifest in sync

`catalog.json` mirrors the package list in the app's `PkgManager.kt`
(`data/PkgManager.kt`). Regenerate it from the app sources:

    python3 scripts/sync_catalog.py <path-to-app>/app/src/main/java/com/weltekxdev/linuxdict/app/data/PkgManager.kt

## Deploying to a new owner

From an authenticated `gh` CLI, so Pages serves from `main` (root):

    gh repo create <owner>/termux-custom-mirror --public --source=. --remote=origin --push
    gh api --method POST repos/<owner>/termux-custom-mirror/pages --input - <<'JSON'
    {"source": {"branch": "main", "path": "/"}}
    JSON

`signed-by` validation uses `key/linuxdict-signing-key.gpg`, committed next to
`dists/` so any tool (or the app installer bootstrap) can bundle it.