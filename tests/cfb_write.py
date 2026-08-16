#!/usr/bin/env python
"""Minimal OLE2 / Compound File Binary (CFB) writer.

Only the subset needed to produce a small, valid OLE2 container whose
children are plain streams stored in the mini-stream. This is sufficient
to build a synthetic Outlook .msg fixture that `olefile.OleFileIO` can
open and whose named property streams MarkItDown's OutlookMsgConverter
can read.

Why hand-rolled: the available libraries (`olefile`, `compoundfiles`)
are read-only. A real .msg is just a CFB with specific stream names, so
a minimal writer is enough and keeps the fixture reproducible offline.

Format references: MS-CFB (Compound File Binary Format).
"""

import struct

SECTOR = 512
MINI = 64
MINI_CUTOFF = 4096

# Use the SAME sentinel values as the installed `olefile` reader. olefile 0.47
# ships a non-standard mapping (FREESECT=0xFFFFFFFF, FATSECT=0xFFFFFFFD), which
# differs from the MS-CFB nominal values. Importing from olefile keeps the
# writer compatible with whatever version actually parses the fixture.
try:
    from olefile import FREESECT, ENDOFCHAIN, FATSECT, DIFSECT  # type: ignore
except Exception:  # pragma: no cover - fallback to this olefile's mapping
    FREESECT = 0xFFFFFFFF
    ENDOFCHAIN = 0xFFFFFFFE
    FATSECT = 0xFFFFFFFD
    DIFSECT = 0xFFFFFFFC


def _dir_entry(name, obj_type, start, size, left=0xFFFFFFFF, right=0xFFFFFFFF,
               child=0xFFFFFFFF, color=1):
    name_u = name.encode("utf-16-le") + b"\x00\x00"
    buf = bytearray(128)
    buf[0:len(name_u)] = name_u
    struct.pack_into("<H", buf, 64, len(name_u))   # NameLength
    buf[66] = obj_type                              # 1=storage 2=stream 5=root
    buf[67] = color
    struct.pack_into("<I", buf, 68, left)
    struct.pack_into("<I", buf, 72, right)
    struct.pack_into("<I", buf, 76, child)
    struct.pack_into("<I", buf, 116, start)
    struct.pack_into("<Q", buf, 120, size)
    return bytes(buf)


def write_cfb(path, streams):
    """Write a CFB file containing `streams` (ordered dict name -> bytes).

    All streams are stored in the mini-stream (they are small). The root
    storage's StartingSector/StreamSize describe the mini-stream container.
    """
    # 1) Assemble mini-stream and mini-FAT.
    mini_chain = []
    mini_fat = []
    start_mini = {}
    size_map = {}
    idx = 0
    for name, data in streams.items():
        size_map[name] = len(data)
        pad = (MINI - (len(data) % MINI)) % MINI
        chunk = data + b"\x00" * pad
        k = len(chunk) // MINI
        start_mini[name] = idx
        for j in range(k):
            mini_chain.append(chunk[j * MINI:(j + 1) * MINI])
            mini_fat.append(ENDOFCHAIN if j == k - 1 else idx + j + 1)
        idx += k
    mini_count = idx
    mini_stream = b"".join(mini_chain)
    pad_ms = (SECTOR - (len(mini_stream) % SECTOR)) % SECTOR
    mini_stream_padded = mini_stream + b"\x00" * pad_ms
    ms_sectors = len(mini_stream_padded) // SECTOR

    # 2) Directory entries: root storage (index 0) + one entry per stream.
    dirs = [{"name": "Root Entry", "type": 5, "start": 0, "size": 0,
             "left": 0xFFFFFFFF, "right": 0xFFFFFFFF, "child": 0xFFFFFFFF}]
    for name, _ in streams.items():
        dirs.append({"name": name, "type": 2, "start": start_mini[name],
                     "size": size_map[name], "left": 0xFFFFFFFF,
                     "right": 0xFFFFFFFF, "child": 0xFFFFFFFF})
    # root child = first stream entry; chain stream siblings via RightSibling.
    if len(dirs) > 1:
        dirs[0]["child"] = 1
        for i in range(1, len(dirs) - 1):
            dirs[i]["right"] = i + 1

    per_sector = SECTOR // 128  # 4 entries per 512-byte directory sector
    d = (len(dirs) + per_sector - 1) // per_sector

    # 3) Normal sector layout. Data sectors are 0-based; the 512-byte header
    #    is NOT a FAT sector and lives at file offset 0. A data sector with
    #    id N is stored at file offset (N+1)*SECTOR (per MS-CFB).
    mf = (mini_count + (SECTOR // 4) - 1) // (SECTOR // 4)  # mini-FAT sectors (128 entries/sector)

    def _layout(f):
        fat_start = 0
        dir_start = fat_start + f
        mf_start = dir_start + d
        ms_start = mf_start + mf
        return fat_start, dir_start, mf_start, ms_start

    f = 1
    fat_start, dir_start, mf_start, ms_start = _layout(f)
    data_sectors = f + d + mf + ms_sectors
    while data_sectors > f * (SECTOR // 4):
        f += 1
        fat_start, dir_start, mf_start, ms_start = _layout(f)
        data_sectors = f + d + mf + ms_sectors

    # 4) FAT.
    fat = [FREESECT] * (f * (SECTOR // 4))
    for i in range(f):                      # FAT sectors are themselves marked
        fat[fat_start + i] = FATSECT
    for i in range(d):                      # directory sector chain
        fat[dir_start + i] = dir_start + i + 1 if i + 1 < d else ENDOFCHAIN
    for i in range(mf):                     # mini-FAT sector chain
        fat[mf_start + i] = ENDOFCHAIN if i + 1 == mf else mf_start + i + 1
    for i in range(ms_sectors):             # mini-stream sector chain
        fat[ms_start + i] = ENDOFCHAIN if i + 1 == ms_sectors else ms_start + i + 1

    # root entry describes the mini-stream container
    dirs[0]["start"] = ms_start
    dirs[0]["size"] = mini_count * MINI

    # 5) Serialize directory sectors.
    dir_bytes = bytearray()
    for s in range(d):
        for e in range(per_sector):
            gi = s * per_sector + e
            if gi < len(dirs):
                en = dirs[gi]
                dir_bytes += _dir_entry(en["name"], en["type"], en["start"],
                                        en["size"], en["left"], en["right"],
                                        en["child"])
            else:
                dir_bytes += b"\x00" * 128
    assert len(dir_bytes) == d * SECTOR

    # mini-FAT sectors
    minifat_bytes = bytearray()
    for i in range(mf * (SECTOR // 4)):
        minifat_bytes += struct.pack("<I", mini_fat[i] if i < len(mini_fat) else FREESECT)
    assert len(minifat_bytes) == mf * SECTOR

    # 6) Header.
    header = bytearray(SECTOR)
    header[0:8] = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
    struct.pack_into("<H", header, 24, 0x003E)   # minor version
    struct.pack_into("<H", header, 26, 3)        # major version
    header[28:30] = b"\xFE\xFF"                  # byte order (LE)
    struct.pack_into("<H", header, 30, 9)        # sector shift
    struct.pack_into("<H", header, 32, 6)        # mini sector shift
    struct.pack_into("<I", header, 44, f)        # number of FAT sectors
    struct.pack_into("<I", header, 48, dir_start)  # first directory sector
    struct.pack_into("<I", header, 56, MINI_CUTOFF)  # mini stream cutoff
    struct.pack_into("<I", header, 60, mf_start)  # first mini-FAT sector
    struct.pack_into("<I", header, 64, mf)       # number of mini-FAT sectors
    struct.pack_into("<I", header, 68, ENDOFCHAIN)  # first DIFAT sector
    struct.pack_into("<I", header, 72, 0)        # number of DIFAT sectors
    # DIFAT: first entry = FAT sector start, rest FREE.
    for i in range(109):
        off = 76 + i * 4
        if i < f:
            struct.pack_into("<I", header, off, fat_start + i)
        else:
            struct.pack_into("<I", header, off, FREESECT)

    # 7) Assemble file: header + FAT sectors + dir + minifat + ministream.
    fat_bytes = b"".join(struct.pack("<I", x) for x in fat)
    out = header + fat_bytes + bytes(dir_bytes) + bytes(minifat_bytes) \
        + mini_stream_padded
    with open(path, "wb") as fh:
        fh.write(out)
    return {"size": len(out), "sectors": 1 + data_sectors, "mini_sectors": mini_count}
