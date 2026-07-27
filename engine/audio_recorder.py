# -*- coding: utf-8 -*-
"""
audio_recorder.py — record the default microphone (e.g. an earphone mic) on
Windows using the built-in winmm / MCI API via ctypes.

No third-party dependency, no PortAudio, no numpy — so nothing changes in the
PyInstaller build. Produces a small mono 16 kHz 16-bit WAV, ideal for speech
transcription by Gemini.
"""

import os
import tempfile

try:
    import ctypes
    from ctypes import wintypes
    _winmm = ctypes.windll.winmm
    _mci = _winmm.mciSendStringW
    _mci.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
    _mci.restype = wintypes.DWORD
    HAVE_MCI = True
except Exception:  # non-Windows or no winmm
    HAVE_MCI = False


class RecorderError(Exception):
    pass


class MicRecorder:
    """Toggle-style recorder: start() then stop() -> path to a WAV file."""

    def __init__(self):
        self._alias = "sinhala_rec"
        self._recording = False

    @property
    def is_recording(self):
        return self._recording

    @property
    def available(self):
        return HAVE_MCI

    def _send(self, command):
        buf = ctypes.create_unicode_buffer(255)
        err = _mci(command, buf, 254, None)
        return int(err), buf.value

    def _error_text(self, code):
        buf = ctypes.create_unicode_buffer(255)
        try:
            _winmm.mciGetErrorStringW(code, buf, 254)
            return buf.value or ("MCI error %d" % code)
        except Exception:
            return "MCI error %d" % code

    def start(self):
        if not HAVE_MCI:
            raise RecorderError("Voice typing is available on Windows only.")
        if self._recording:
            return
        # Close any leftover device from a previous session, then open fresh.
        self._send("close %s" % self._alias)
        err, _ = self._send("open new type waveaudio alias %s" % self._alias)
        if err:
            raise RecorderError("Cannot open the microphone: " + self._error_text(err))
        self._send("set %s time format ms" % self._alias)
        # Try speech-friendly formats in order; each is best-effort. If a device
        # rejects them all we still record at its DEFAULT format (a valid WAV).
        for fmt in ("bitspersample 16 channels 1 samplespersec 16000",
                    "bitspersample 16 channels 1 samplespersec 44100",
                    "bitspersample 16 channels 2 samplespersec 44100"):
            e2, _ = self._send("set %s %s" % (self._alias, fmt))
            if not e2:
                break
        err, _ = self._send("record %s" % self._alias)
        if err:
            msg = self._error_text(err)
            self._send("close %s" % self._alias)
            raise RecorderError(
                "Cannot start recording: " + msg +
                "  (Set your microphone as the default recording device in "
                "Windows Sound settings, then try again.)")
        self._recording = True

    def stop(self):
        """Stop recording and return the path to a saved WAV file (or None)."""
        if not self._recording:
            return None
        self._send("stop %s" % self._alias)
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="sinhala_voice_")
        os.close(fd)
        err, _ = self._send('save %s "%s"' % (self._alias, path))
        self._send("close %s" % self._alias)
        self._recording = False
        if err:
            try:
                os.remove(path)
            except OSError:
                pass
            raise RecorderError("Cannot save the recording: " + self._error_text(err))
        return path

    def cancel(self):
        """Abort without saving."""
        if self._recording:
            self._send("stop %s" % self._alias)
            self._send("close %s" % self._alias)
            self._recording = False
