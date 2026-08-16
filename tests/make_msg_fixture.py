#!/usr/bin/env python
"""Generate a minimal but valid Outlook .msg OLE2 fixture.

MdDesk / MarkItDown's OutlookMsgConverter (`_outlook_msg_converter.py`)
extracts four property streams by fixed names and decodes them as
UTF-16-LE:

    __substg1.0_0C1F001F  -> From    (PidTagSenderName)
    __substg1.0_0E04001F  -> To      (PidTagDisplayTo)
    __substg1.0_0037001F  -> Subject (PidTagSubject)
    __substg1.0_1000001F  -> Body    (PidTagBody)

This script writes those streams (plus a minimal property stream header)
into a standard OLE2 / Compound File using `compoundfiles`, producing a
file that `olefile.OleFileIO` can open and the converter can read.

The .msg extension makes `accepts()` short-circuit to True, so the
brute-force OLE/Outlook checks are not required for acceptance.

Usage:
    python tests/make_msg_fixture.py [output_path]
"""
import os
import sys

from cfb_write import write_cfb

# Fixed property-stream names used by MarkItDown's OutlookMsgConverter.
STREAMS = {
    "__substg1.0_0C1F001F": "Alice Example <alice@example.com>",
    "__substg1.0_0E04001F": "Bob Recipient <bob@example.com>",
    "__substg1.0_0037001F": "Quarterly Report Reminder",
    "__substg1.0_1000001F": (
        "Hi Bob,\n\n"
        "Please find the quarterly report attached. "
        "Let me know if you have any questions.\n\n"
        "Best regards,\nAlice"
    ),
}


def build(out_path: str) -> None:
    # Ordered stream set. `__properties_version1.0` is a minimal property
    # stream header (content is ignored by the converter; only presence
    # matters). The four `__substg1.0_*` streams are what OutlookMsgConverter
    # reads; Outlook stores 001F (Unicode) properties as UTF-16-LE.
    streams = {"__properties_version1.0": b"\x00" * 16}
    for name, text in STREAMS.items():
        streams[name] = text.encode("utf-16-le")
    info = write_cfb(out_path, streams)
    return info


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, "fixtures", "sample_outlook.msg")
    out = sys.argv[1] if len(sys.argv) > 1 else default
    os.makedirs(os.path.dirname(out), exist_ok=True)
    info = build(out)
    size = os.path.getsize(out)
    print(f"MSG_FIXTURE_WRITTEN path={out} size_bytes={size} sectors={info['sectors']} mini_sectors={info['mini_sectors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
