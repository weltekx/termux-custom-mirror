#!/usr/bin/env python3
"""Build a signed APT mirror for LinuxDictApp.

Fetches the real Termux aarch64 package index, resolves dependency closures
for a curated set of packages, downloads the .debs into pool/, and renders a
signed dists/ tree using the project's own GPG signing key:

    dists/stable/main/binary-<arch>/Packages (+ .gz)
    dists/stable/Release            (plain, checksummed)
    dists/stable/InRelease          (clearsigned Release)

Packages in the catalog that have a hosted .deb get full real fields
(Filename/Size/SHA256/architecture/etc). The rest stay metadata-only stanzas
(apt reports "no installation candidate" for them).
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

TERMUX_INDEX_URL = "https://packages-cf.termux.dev/apt/termux-main/dists/stable/main/binary-aarch64/Packages"
TERMUX_POOL_BASE = "https://packages-cf.termux.dev/apt/termux-main"
ABIS = ["aarch64", "arm", "x86_64", "x86"]
UA = "Mozilla/5.0 (Linux; Android 13) LinuxDictApp-mirror/1.0"


def http_fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as src, open(dest, "wb") as out:
        while True:
            chunk = src.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def parse_packages(path):
    pkgs = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        stanza = {}
        for line in fh:
            if line.strip() == "":
                if stanza:
                    pkgs[stanza["Package"]] = stanza
                    stanza = {}
                continue
            if line.startswith(" ") or line.startswith("\t"):
                # continuation: append to last key
                key = list(stanza.keys())[-1] if stanza else None
                if key:
                    stanza[key] += "\n" + line.strip()
                continue
            k, _, v = line.partition(":")
            stanza[k.strip()] = v.strip()
    if stanza:
        pkgs[stanza.get("Package")] = stanza
    return pkgs


def parse_depends(dep_str, index):
    """Resolve a Depends string to the concrete package names to fetch."""
    if not dep_str:
        return []
    out = []
    for group in dep_str.split(","):
        group = group.strip()
        if not group:
            continue
        alternatives = [a.strip().split(" ", 1)[0] for a in group.split("|")]
        for alt in alternatives:
            if alt in index:
                out.append(alt)
                break
    return out


def closure(start, index, exclude):
    want = set()
    stack = [p for p in start if p in index]
    while stack:
        name = stack.pop()
        if name in want or name in exclude:
            continue
        want.add(name)
        stack.extend(parse_depends(index[name].get("Depends", ""), index))
    return want


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gpg_sign(gnupg_home, data_path, out_path):
    env = dict(os.environ, GNUPGHOME=gnupg_home)
    with open(data_path, "rb") as src, open(out_path, "wb") as dst:
        subprocess.run(
            [
                "gpg", "--batch", "--armor", "--clearsign", "--digest-algo", "SHA512",
                # Pin the signature timestamp so InRelease is byte-reproducible
                # across local and CI builds (prevents the auto-commit loop).
                # Must be >= this key's creation time (2026-09-12T18:00Z) —
                # 2026-09-12T23:59:59Z.
                "--faked-system-time", "1789257599",
            ],
            stdin=src, stdout=dst, check=True, env=env,
        )


def stanza_from_index(entry, filename, size, sha):
    package = entry["Package"]
    lines = [
        f"Package: {package}",
        f"Version: {entry['Version']}",
        f"Architecture: {entry.get('Architecture', 'aarch64')}",
        f"Maintainer: {entry.get('Maintainer', 'LinuxDictApp')}",
        f"Installed-Size: {entry.get('Installed-Size', '1')}",
        f"Size: {size}",
        f"SHA256: {sha}",
        f"Filename: {filename}",
    ]
    for field in ("Priority", "Section", "Essential"):
        if entry.get(field):
            lines.append(f"{field}: {entry[field]}")
    deps = entry.get("Depends")
    lines.append(f"Depends: {deps}" if deps else "Depends:")
    if entry.get("Recommends"):
        lines.append(f"Recommends: {entry['Recommends']}")
    if entry.get("Homepage"):
        lines.append(f"Homepage: {entry['Homepage']}")
    lines.append(f"Description: {entry.get('Description-short', entry.get('Description', ''))}")
    return "\n".join(lines) + "\n\n"


def metadata_stanza(pkg):
    name = pkg["name"]
    deps = ", ".join(pkg.get("depends", []))
    lines = [
        f"Package: {name}",
        f"Version: {pkg['version']}",
        f"Architecture: all",
        f"Maintainer: LinuxDictApp",
        f"Installed-Size: {in_kb(pkg.get('size', '0'))}",
        "Depends: " + deps if deps else "Depends:",
        f"Description: {pkg.get('description', '')}",
    ]
    return "\n".join(lines) + "\n\n"


def in_kb(size):
    try:
        parts = size.split()
        value = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else "KB"
        mult = {"B": 1, "KB": 1, "MB": 1024, "GB": 1024 * 1024}.get(unit, 1)
        return str(int(value * mult))
    except Exception:
        return "1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--gnupghome", default=os.environ.get("GNUPGHOME"))
    ap.add_argument("--index-cache", default=None)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not args.gnupghome:
        print("error: --gnupghome (or GNUPGHOME) is required for signing")
        return 1

    with open(os.path.join(root, "catalog.json"), encoding="utf-8") as fh:
        catalog = json.load(fh)["packages"]

    # ── curated pool list + already-installed (bootstrap) set ───────────
    curated = [
        l.strip()
        for l in open(os.path.join(root, "curated", "pool.txt"), encoding="utf-8")
        if l.strip() and not l.strip().startswith("#")
    ]
    installed_file = os.path.join(root, "curated", "installed.txt")
    installed = set()
    if os.path.exists(installed_file):
        installed = {l.strip() for l in open(installed_file, encoding="utf-8") if l.strip()}

    # ── fetch / parse termux index ───────────────────────────────────────
    cache_path = args.index_cache or os.path.join(root, ".cache", "termux-aarch64-Packages")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    if args.skip_download and os.path.exists(cache_path):
        print("using cached termux index")
    else:
        print(f"fetching {TERMUX_INDEX_URL}")
        http_fetch(TERMUX_INDEX_URL, cache_path)
    index = parse_packages(cache_path)
    print(f"termux index: {len(index)} packages")

    # ── resolve closure ──────────────────────────────────────────────────
    want = closure([p for p in curated if p not in installed], index, exclude=installed)
    missing = [p for p in curated if p not in index]
    if missing:
        print("warning: curated packages not in termux index:", missing)
    print(f"pool closure: {len(want)} packages (incl {len(curated)} curated)")

    # ── download debs ────────────────────────────────────────────────────
    pool_dir = os.path.join(root, "pool", "aarch64")
    os.makedirs(pool_dir, exist_ok=True)
    pool_meta = {}
    for name in sorted(want):
        entry = index[name]
        remote = entry.get("Filename")
        if not remote:
            print(f"  ! {name}: no Filename in index; skipping")
            continue
        deb_name = os.path.basename(remote)
        local = os.path.join(pool_dir, deb_name)
        if not os.path.exists(local) or os.path.getsize(local) < 50:
            url = TERMUX_POOL_BASE + "/" + remote
            print(f"  fetch {deb_name}")
            http_fetch(url, local)
        pool_meta[name] = {
            "entry": entry,
            "filename": "pool/aarch64/" + deb_name,
            "size": os.path.getsize(local),
            "sha256": sha256_of(local),
        }
    print(f"pool ready: {len(pool_meta)} debs")

    # ── catalog name set for metadata-only fallback ──────────────────────
    catalog_names = {p["name"] for p in catalog}
    catalog_by_name = {p["name"]: p for p in catalog}

    # ── render Packages per ABI ──────────────────────────────────────────
    dists = os.path.join(root, "dists", "stable", "main")
    release_files = []
    for abi in ABIS:
        out_dir = os.path.join(dists, "binary-" + abi)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "Packages")
        real_arch = abi == "aarch64"
        with open(out_path, "w", encoding="utf-8") as out:
            if real_arch:
                # Real stanzas for every .deb in the pool (curated + transitive).
                for name in sorted(pool_meta):
                    info = pool_meta[name]
                    out.write(stanza_from_index(
                        info["entry"], info["filename"], info["size"], info["sha256"]
                    ))
                # Metadata-only stanzas for catalog packages we do not host yet.
                for pkg in sorted(catalog, key=lambda p: p["name"]):
                    if pkg["name"] not in pool_meta:
                        out.write(metadata_stanza(pkg))
            else:
                for pkg in sorted(catalog, key=lambda p: p["name"]):
                    out.write(metadata_stanza(pkg))
        gz_path = out_path + ".gz"
        with open(out_path, "rb") as src, gzip.GzipFile(filename=gz_path, mode="wb", mtime=0) as dst:
            dst.write(src.read())
        measure(out_path, gz_path, release_files, f"main/binary-{abi}")
        print(f"wrote {out_path}" + (f" (+{len(pool_meta)} real entries)" if real_arch else " (metadata-only)"))
        print(f"wrote {gz_path}")

    # ── Release file ─────────────────────────────────────────────────────
    release = os.path.join(root, "dists", "stable", "Release")
    # Fixed (reproducible) date so a rebuild with unchanged inputs produces
    # a byte-identical Release/InRelease and the CI commit-push loop settles.
    now = "Sat, 12 Sep 2026 00:00:00 +0000"
    with open(release, "w", encoding="utf-8") as out:
        out.write("Origin: LinuxDictApp Custom Mirror\n")
        out.write("Label: LinuxDictApp Custom Mirror\n")
        out.write(f"Suite: stable\nCodename: stable\nVersion: 1.0\n")
        out.write(f"Date: {now}\n")
        out.write(f"Architectures: {' '.join(ABIS)}\n")
        out.write("Components: main\n")
        out.write("Description: LinuxDictApp signed package mirror\n")
        for alg in ("MD5Sum", "SHA1", "SHA256", "SHA512"):
            out.write(alg + ":\n")
            for relpath, size, h, alg_ in release_files:
                if alg_ != alg:
                    continue
                out.write(f" {h} {size:14} {relpath}\n")
    print(f"wrote {release}")

    # ── InRelease (clearsigned) ──────────────────────────────────────────
    inrelease = os.path.join(root, "dists", "stable", "InRelease")
    gpg_sign(args.gnupghome, release, inrelease)
    print(f"signed {inrelease}")

    # ── verify with gpgv ─────────────────────────────────────────────────
    keyring = os.path.join(root, "key", "linuxdict-signing-key.gpg")
    if os.path.exists(keyring):
        subprocess.run(
            ["gpgv", "--keyring", keyring, inrelease],
            check=True,
            capture_output=True,
        )
        print("gpgv: InRelease signature OK")
    return 0


def measure(pkgs_path, pkgs_gz, out, relprefix):
    for path in (pkgs_path, pkgs_gz):
        rel = relprefix + "/" + os.path.basename(path)
        out.append(entry_for(path, rel, "MD5Sum"))
        out.append(entry_for(path, rel, "SHA1"))
        out.append(entry_for(path, rel, "SHA256"))
        out.append(entry_for(path, rel, "SHA512"))


_ALGOS = {"MD5Sum": "md5", "SHA1": "sha1", "SHA256": "sha256", "SHA512": "sha512"}


def entry_for(path, rel, alg):
    import hashlib as _h
    h = _h.new(_ALGOS[alg])
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return (rel, os.path.getsize(path), h.hexdigest(), alg)


if __name__ == "__main__":
    sys.exit(main())