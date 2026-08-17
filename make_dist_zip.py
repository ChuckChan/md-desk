#!/usr/bin/env python
"""Distribution ZIP builder for MdDesk v0.3.

Packs the full frozen app directory + RELEASE.md + README.txt + README.md into
a single top-level folder inside the ZIP. Pure stdlib, no external deps.
"""
import os
import zipfile

BASE = r"D:\WB\2026-08-16-02-02-20\markitdown-gui"
SRC_DIST = os.path.join(BASE, "dist", "md-desk")
RELEASE_MD = os.path.join(BASE, "RELEASE.md")
README_TXT = os.path.join(BASE, "README.txt")
README_MD = os.path.join(BASE, "README.md")
OUT = os.path.join(BASE, "MdDesk-v0.3-Windows-x64.zip")
ROOT = "MdDesk-v0.3"


def add_dir(zf, path, arcroot):
    count = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, path)
            arc = "/".join([arcroot, rel.replace("\\", "/")])
            zf.write(full, arc)
            count += 1
    return count


def main():
    for p in (SRC_DIST, RELEASE_MD, README_TXT, README_MD):
        if not os.path.exists(p):
            raise SystemExit(f"MISSING: {p}")

    # ZipFile "w" mode truncates/overwrites the target, so no explicit
    # deletion is needed (avoids sandbox SAFE_DELETE blocking on re-runs).
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        n_dist = add_dir(zf, SRC_DIST, "/".join([ROOT, "md-desk"]))
        zf.write(RELEASE_MD, "/".join([ROOT, "RELEASE.md"]))
        zf.write(README_TXT, "/".join([ROOT, "README.txt"]))
        zf.write(README_MD, "/".join([ROOT, "README.md"]))

    size = os.path.getsize(OUT)
    print(f"ZIP_OK files_in_dist={n_dist} size_bytes={size} path={OUT}")


if __name__ == "__main__":
    main()
