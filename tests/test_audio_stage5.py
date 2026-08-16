#!/usr/bin/env python
"""Stage 5 — Audio transcription tests (source level, Qt-free).

Verifies the MdDesk audio path WITHOUT modifying upstream markitdown:

  * WAV is detected by the engine audio converter and reaches the
    speech-recognition step (real markitdown engine, mocked Google SR).
  * MP3 without FFmpeg does NOT crash and yields a friendly error.
  * Each failure category surfaces a distinct, friendly Chinese message:
      - missing dependency (pydub / speech_recognition absent)
      - missing FFmpeg (decode failure)
      - network failure (recognize_google -> RequestError)
      - no speech detected (recognize_google -> UnknownValueError)
  * Regression gate: previously-PASSING format tests still pass.

Google SR itself requires network + real speech; we stub `recognize_google`
so the transcription *pipeline* (engine audio converter -> pydub/sr.record ->
recognizer call -> transcript embedded in markdown) is exercised deterministically.

Run from project root:
    python tests/test_audio_stage5.py
"""

import os
import sys
import wave
import struct
import math
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIX = ROOT / "tests" / "fixtures"


def _make_tone_wav(path: Path, hz=440.0, sr=16000, dur=1.0):
    samples = [int(30000 * math.sin(2 * math.pi * hz * t / sr))
               for t in range(int(sr * dur))]
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _wav_transcript_test():
    """WAV reaches the SR step and embeds the transcript (Google mocked)."""
    import speech_recognition as sr
    from src.converter import convert_file

    p = FIX / "sample_speech.wav"
    if not p.exists():
        _make_tone_wav(p)

    transcript = "hello from the mocked speech recognition"
    with mock.patch.object(sr.Recognizer, "recognize_google",
                           return_value=transcript) as m:
        md = convert_file(str(p))
        ok = True
        ok &= _check("AUDIO_WAV_ENGAGES_SR", m.called,
                     "recognize_google was not called for WAV")
        ok &= _check("AUDIO_WAV_TRANSCRIPT_EMBEDDED",
                     ("### Audio Transcript:" in md) and (transcript in md),
                     "transcript block missing: " + repr(md[:120]))
        return ok


def _mp3_no_ffmpeg_test():
    """MP3 decode without FFmpeg must not crash; friendly error returned."""
    from src.converter import convert_file, ConversionError
    from src.file_entry import FileStatus
    if not (FIX / "sample_speech.mp3").exists():
        (FIX / "sample_speech.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 2000)
    try:
        convert_file(str(FIX / "sample_speech.mp3"))
        # If it somehow succeeded (ffmpeg present), that's also acceptable.
        _check("AUDIO_MP3_NOFFMPEG_NO_CRASH", True,
               "mp3 converted (ffmpeg present)")
        return True
    except ConversionError as e:
        ok = True
        ok &= _check("AUDIO_MP3_NOFFMPEG_ERROR", e.status == FileStatus.ERROR,
                     f"status={e.status}")
        ok &= _check("AUDIO_MP3_NOFFMPEG_FRIENDLY",
                     ("FFmpeg" in e.message or "ffmpeg" in e.message
                      or "解码" in e.message),
                     "message not FFmpeg-friendly: " + e.message)
        return ok
    except Exception as e:  # pragma: no cover
        _check("AUDIO_MP3_NOFFMPEG_NO_CRASH", False,
               f"unexpected {type(e).__name__}: {e}")
        return False


def _friendly_messages_test():
    """Each failure category yields a distinct friendly message."""
    from src.converter import map_exception, ConversionError
    from src.file_entry import FileStatus
    from markitdown import (
        FileConversionException, MissingDependencyException,
    )
    import speech_recognition as sr

    ok = True

    # 1) Missing dependency. NOTE: the message must NOT contain "pydub"/
    #    "ffmpeg"/"decode"/"找不到" etc., otherwise it would be misclassified
    #    into the FFmpeg/decode branch. Real MissingDependencyException messages
    #    from markitdown do not contain those tokens.
    e = MissingDependencyException("missing audio transcription dependencies")
    status, msg = map_exception(e)
    ok &= _check("MSG_MISSING_DEP",
                 status == FileStatus.ERROR and "audio-transcription" in msg,
                 msg)

    # 2) Missing FFmpeg (FileNotFoundError from pydub spawning ffmpeg).
    fnf = FileNotFoundError("[WinError 2] 系统找不到指定的文件。")
    fnf.__cause__ = None
    wrapped = FileConversionException(
        f"AudioConverter threw FileNotFoundError with message: {fnf}"
    )
    # Build a wrapper whose __cause__ chain carries FileNotFoundError.
    class _W(FileConversionException):
        pass
    w = _W(f"AudioConverter threw FileNotFoundError with message: {fnf}")
    w.__cause__ = fnf
    status, msg = map_exception(w)
    ok &= _check("MSG_MISSING_FFMPEG",
                 status == FileStatus.ERROR and ("FFmpeg" in msg or "ffmpeg" in msg),
                 msg)

    # 3) Network failure -> RequestError.
    req = sr.RequestError("recognition request failed")
    w2 = _W(f"AudioConverter threw RequestError with message: {req}")
    w2.__cause__ = req
    status, msg = map_exception(w2)
    ok &= _check("MSG_NETWORK_FAIL",
                 status == FileStatus.ERROR and "Google" in msg and "联网" in msg,
                 msg)

    # 4) No speech -> UnknownValueError.
    unk = sr.UnknownValueError()
    w3 = _W(f"AudioConverter threw UnknownValueError with message: {unk}")
    w3.__cause__ = unk
    status, msg = map_exception(w3)
    ok &= _check("MSG_NO_SPEECH",
                 status == FileStatus.ERROR and "语音" in msg,
                 msg)
    return ok


def _regression_gate():
    """Previously-PASSING format tests must remain green (Stage 4 gate)."""
    import subprocess
    gate = [
        "tests/test_converter.py",
        "tests/test_worker.py",
        "tests/test_stage3_integration.py",
        "tests/test_regression_formats.py",
        "tests/test_advanced_settings.py",
    ]
    ok = True
    py = sys.executable
    for t in gate:
        tp = ROOT / t
        if not tp.exists():
            print("SKIP -", t, "(absent)")
            continue
        r = subprocess.run([py, str(tp)], capture_output=True, text=True)
        passed = (r.returncode == 0)
        ok &= _check(f"REGRESSION {t}", passed,
                     (r.stdout + r.stderr)[-200:] if not passed else "")
        if not passed:
            print("    --- tail ---")
            print((r.stdout + r.stderr)[-800:])
    return ok


def main():
    ok = True
    ok &= _wav_transcript_test()
    ok &= _mp3_no_ffmpeg_test()
    ok &= _friendly_messages_test()
    ok &= _regression_gate()
    print()
    print("ALL STAGE 5 AUDIO CHECKS PASSED" if ok else "SOME STAGE 5 AUDIO CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
