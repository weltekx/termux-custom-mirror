#!/usr/bin/env python3
"""Sync catalog.json from the app's PkgManager.kt catalog.

Usage:
    python3 scripts/sync_catalog.py <path-to-PkgManager.kt>
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse(kt_path: str) -> list:
    with open(kt_path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("object PkgManager")
    end = text.index("// ── Custom APT mirror sync", start)
    body = text[start:end]

    pat = re.compile(
        r'LinuxPackage\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",'
        r'\s*listOf\(([^)]*)\),\s*"((?:[^"\\]|\\.)*)"\s*\)',
        re.S,
    )
    packages = []
    for m in pat.finditer(body):
        name, version, size, deps_str, desc = m.groups()
        deps = [d.strip().strip('"') for d in deps_str.split(",") if d.strip()]
        packages.append({
            "name": name,
            "version": version,
            "size": size,
            "depends": deps,
            "description": desc,
        })
    packages.sort(key=lambda p: p["name"])
    seen = set()
    unique = []
    for p in packages:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique.append(p)
    return unique


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    packages = parse(sys.argv[1])
    payload = {"suite": "stable", "packages": packages}
    out_path = os.path.join(ROOT, "catalog.json")
    with open(out_path, "w", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(f"wrote {out_path} ({len(packages)} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())