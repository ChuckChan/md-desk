#!/usr/bin/env python
"""Verify the distribution ZIP: extract, check structure, offscreen boot, hash."""
import os
import sys
import zipfile
import hashlib
import subprocess

BASE = r"D:\WB\2026-08-16-02-02-20\markitdown-gui"
ZIP = os.path.join(BASE, "MdDesk-v0.3-Windows-x64.zip")
ROOT = "MdDesk-v0.3"
EXTRACT = r"D:\_dist_verify"
EXE = os.path.join(EXTRACT, ROOT, "md-desk", "md-desk.exe")
INTERNAL = os.path.join(EXTRACT, ROOT, "md-desk", "_internal")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    # 1) hash
    digest = sha256(ZIP)
    size = os.path.getsize(ZIP)
    print(f"ZIP size_bytes={size}")
    print(f"ZIP sha256={digest}")

    # 2) extract (overwrite existing extract dir if present)
    if os.path.isdir(EXTRACT):
        import shutil
        shutil.rmtree(EXTRACT)
    os.makedirs(EXTRACT, exist_ok=True)
    with zipfile.ZipFile(ZIP, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise SystemExit(f"CORRUPT_ENTRY: {bad}")
        zf.extractall(EXTRACT)
    print("EXTRACT_OK")

    # 3) structure checks
    assert os.path.isfile(EXE), f"MISSING exe: {EXE}"
    assert os.path.isdir(INTERNAL), f"MISSING _internal: {INTERNAL}"
    assert os.path.isfile(os.path.join(EXTRACT, ROOT, "RELEASE.md"))
    assert os.path.isfile(os.path.join(EXTRACT, ROOT, "README.txt"))
    assert os.path.isfile(os.path.join(EXTRACT, ROOT, "README.md"))
    print("STRUCTURE_OK exe+_internal+RELEASE.md+README.txt+README.md present")

    # 4) offscreen boot
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    p = subprocess.Popen([EXE], env=env)
    try:
        rc = p.wait(timeout=8)
        print(f"BOOT_EXITED_IMMEDIATELY rc={rc}")
        ok = rc == 0
    except subprocess.TimeoutExpired:
        print(f"BOOT_OK still_running pid={p.pid}")
        ok = True
        p.kill()
    print("BOOT_OK" if ok else "BOOT_FAIL")


if __name__ == "__main__":
    main()
