#!/usr/bin/env python3
"""Generate an APT-compatible mirror tree for LinuxDictApp.

Reads catalog.json (the package manifest maintained in sync with the app's
PkgManager catalog) and renders a Termux-style repository layout:

    dists/stable/main/binary-<arch>/Packages     (one per ABI)

The Packages files follow the Debian control-file stanza format so the app
and `apt`/`dpkg-scanpackages`-based tooling can consume them.
"""
import json
import os
import sys

ABIS = ["aarch64", "arm", "x86_64", "x86"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stanza(pkg: dict) -> str:
    deps = ", ".join(pkg.get("depends", []))
    lines = [
        f"Package: {pkg['name']}",
        f"Version: {pkg['version']}",
        f"Architecture: all",
        f"Maintainer: LinuxDictApp",
        f"Installed-Size: {in_kb(pkg.get('size', '0'))}",
        f"Depends: {deps}" if deps else "Depends:",
        f"Description: {pkg.get('description', '')}",
        "",
    ]
    return "\n".join(lines) + "\n"


def in_kb(size: str) -> str:
    """Convert '3.2 MB' / '640 KB' style sizes to integer KB."""
    try:
        value = float(size.split()[0])
        unit = size.split()[1].upper() if len(size.split()) > 1 else "KB"
        mult = {"B": 1, "KB": 1, "MB": 1024, "GB": 1024 * 1024}.get(unit, 1)
        return str(int(value * mult))
    except Exception:
        return "1"


def main() -> None:
    manifest = os.path.join(ROOT, "catalog.json")
    with open(manifest, encoding="utf-8") as fh:
        data = json.load(fh)
    packages = data["packages"]

    dists = os.path.join(ROOT, "dists", "stable", "main")
    for abi in ABIS:
        out_dir = os.path.join(dists, "binary-" + abi)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "Packages")
        with open(out_path, "w", encoding="utf-8") as out:
            for pkg in sorted(packages, key=lambda p: p["name"]):
                out.write(stanza(pkg))
        print(f"wrote {out_path} ({len(packages)} entries)")


if __name__ == "__main__":
    sys.exit(main())