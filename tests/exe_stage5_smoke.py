"""Frozen-EXE runtime smoke for Stage 5 (Audio transcription).

Built with the SAME collection flags as the real md-desk.exe (see stage5.spec
and build_exe.sh: collects markitdown submodules + explicit pydub /
speech_recognition hidden imports). It proves, inside the frozen binary
(no venv):

  1. pydub / speech_recognition are bundled and importable (hidden imports
     collected by PyInstaller -- collect_submodules markitdown pulls the
     engine audio converter, but we assert the two explicit extras too).
  2. WAV reaches the speech-recognition step and embeds the transcript
     ("### Audio Transcript:" block) -- the transcription *pipeline*
     (engine audio converter -> pydub/sr.record -> recognizer -> markdown)
     is exercised end-to-end. Google SR itself needs real speech + network,
     so we stub `recognize_google` deterministically (same approach as the
     source-level Stage 5 test and all prior frozen stages).
  3. MP3 decode without FFmpeg does NOT crash the frozen EXE; it returns a
     friendly Chinese error (FFmpeg/解码) instead of an unhandled traceback.

stdout/stderr forced to UTF-8 so non-ASCII diagnostics never crash the
harness on a GBK Windows console. Printed labels are ASCII.

Run: build via stage5.spec, then execute the frozen stage5.exe.
"""

import io
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

# Force UTF-8 so any non-ASCII transcript/content never raises
# UnicodeEncodeError on a GBK Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, ".")

from unittest import mock


def _check(label, ok, detail=""):
    print(("PASS" if ok else "FAIL"), "-", label, "" if ok else ":: " + detail)
    return ok


def _make_tone_wav(path: Path, hz=440.0, sr=16000, dur=1.0):
    samples = [int(30000 * math.sin(2 * math.pi * hz * t / sr))
               for t in range(int(sr * dur))]
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def _hidden_imports_tests():
    """Prove pydub + speech_recognition are actually bundled in the EXE."""
    ok = True
    try:
        import pydub  # noqa: F401
        ok &= _check("FROZEN_IMPORT_PYDUB", True)
    except Exception as e:  # pragma: no cover
        ok &= _check("FROZEN_IMPORT_PYDUB", False, f"{type(e).__name__}: {e}")
    try:
        import speech_recognition  # noqa: F401
        ok &= _check("FROZEN_IMPORT_SR", True)
    except Exception as e:  # pragma: no cover
        ok &= _check("FROZEN_IMPORT_SR", False, f"{type(e).__name__}: {e}")
    return ok


def _wav_transcript_test():
    """WAV reaches the SR step and embeds the transcript (Google mocked)."""
    import speech_recognition as sr
    from src.converter import convert_file

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "speech.wav"
        _make_tone_wav(p)
        transcript = "hello from the mocked speech recognition"
        with mock.patch.object(sr.Recognizer, "recognize_google",
                               return_value=transcript) as m:
            md = convert_file(str(p))
            ok = True
            ok &= _check("FROZEN_WAV_ENGAGES_SR", m.called,
                         "recognize_google was not called for WAV")
            ok &= _check("FROZEN_WAV_TRANSCRIPT_EMBEDDED",
                         ("### Audio Transcript:" in md) and (transcript in md),
                         "transcript block missing: " + repr(md[:120]))
            return ok


def _mp3_no_ffmpeg_test():
    """MP3 decode without FFmpeg must not crash; friendly error returned."""
    from src.converter import convert_file, ConversionError
    from src.file_entry import FileStatus

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "speech.mp3"
        p.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 2000)
        try:
            convert_file(str(p))
            # If ffmpeg is present in the frozen runtime, success is fine too.
            _check("FROZEN_MP3_NOFFMPEG_NO_CRASH", True, "mp3 converted (ffmpeg present)")
            return True
        except ConversionError as e:
            ok = True
            ok &= _check("FROZEN_MP3_NOFFMPEG_ERROR", e.status == FileStatus.ERROR,
                         f"status={e.status}")
            ok &= _check("FROZEN_MP3_NOFFMPEG_FRIENDLY",
                         ("FFmpeg" in e.message or "ffmpeg" in e.message
                          or "解码" in e.message),
                         "message not FFmpeg-friendly: " + e.message)
            return ok
        except Exception as e:  # pragma: no cover
            _check("FROZEN_MP3_NOFFMPEG_NO_CRASH", False,
                   f"unexpected {type(e).__name__}: {e}")
            return False


def main():
    ok = True
    ok &= _hidden_imports_tests()
    ok &= _wav_transcript_test()
    ok &= _mp3_no_ffmpeg_test()
    print()
    if ok:
        print("STAGE5_FROZEN_PASS")
        sys.exit(0)
    else:
        print("STAGE5_FROZEN_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
