# -*- coding: utf-8 -*-
"""
audio_recorder.py — record the microphone (built-in or any plugged mic).

Primary backend: sounddevice (PortAudio). It auto-detects the OS default input
device and works with modern Windows audio drivers (WASAPI/WDM). It records raw
int16 PCM (no numpy needed) which we write to a small mono 16 kHz WAV.

Fallback: legacy winmm/MCI (only if sounddevice is unavailable) — kept for
completeness, though MCI's waveaudio often fails on Windows 10/11.
"""

import os
import wave
import tempfile

RATE = 16000
CHANNELS = 1
SAMPWIDTH = 2  # int16

# ----- primary backend: sounddevice -------------------------------------
try:
    import sounddevice as _sd
    HAVE_SD = True
except Exception:
    _sd = None
    HAVE_SD = False

# ----- fallback backend: winmm / MCI ------------------------------------
try:
    import ctypes
    from ctypes import wintypes
    _winmm = ctypes.windll.winmm
    _mci = _winmm.mciSendStringW
    _mci.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
    _mci.restype = wintypes.DWORD
    HAVE_MCI = True
except Exception:
    HAVE_MCI = False


class RecorderError(Exception):
    pass


def _new_wav_path():
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="sinhala_voice_")
    os.close(fd)
    return path


def _pick_input_device():
    """Return the default input device index, or the first device with input
    channels. Raises if the machine has no input device at all."""
    try:
        default_in = _sd.default.device[0]
    except Exception:
        default_in = None
    if default_in is not None and default_in != -1:
        try:
            if _sd.query_devices(default_in).get("max_input_channels", 0) > 0:
                return default_in
        except Exception:
            pass
    for i, dev in enumerate(_sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            return i
    raise RecorderError("No microphone found. Plug in a mic (or enable the "
                        "built-in one) and try again.")


class MicRecorder:
    def __init__(self):
        self._recording = False
        self._frames = []
        self._stream = None
        self._device = None

    @property
    def is_recording(self):
        return self._recording

    @property
    def available(self):
        return HAVE_SD or HAVE_MCI

    # ----- public --------------------------------------------------------
    def start(self):
        if self._recording:
            return
        if HAVE_SD:
            self._start_sd()
        elif HAVE_MCI:
            self._start_mci()
        else:
            raise RecorderError("No audio recording backend available.")
        self._recording = True

    def stop(self):
        if not self._recording:
            return None
        self._recording = False
        if HAVE_SD and self._stream is not None:
            return self._stop_sd()
        if HAVE_MCI:
            return self._stop_mci()
        return None

    def cancel(self):
        try:
            self.stop()
        except Exception:
            pass

    # ----- sounddevice backend ------------------------------------------
    def _start_sd(self):
        self._frames = []
        self._device = _pick_input_device()

        def _cb(indata, frames, time_info, status):
            # indata is a raw cffi buffer (int16 bytes) because dtype='int16'
            self._frames.append(bytes(indata))

        try:
            self._stream = _sd.RawInputStream(
                samplerate=RATE, channels=CHANNELS, dtype="int16",
                device=self._device, callback=_cb, blocksize=0)
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise RecorderError("Cannot start the microphone: %s" % exc)

    def _stop_sd(self):
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        data = b"".join(self._frames)
        self._frames = []
        if not data:
            return None
        path = _new_wav_path()
        with wave.open(path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE)
            wf.writeframes(data)
        return path

    # ----- MCI fallback --------------------------------------------------
    def _mci_send(self, command):
        buf = ctypes.create_unicode_buffer(255)
        err = _mci(command, buf, 254, None)
        return int(err), buf.value

    def _mci_error(self, code):
        buf = ctypes.create_unicode_buffer(255)
        try:
            _winmm.mciGetErrorStringW(code, buf, 254)
            return buf.value or ("MCI error %d" % code)
        except Exception:
            return "MCI error %d" % code

    def _start_mci(self):
        self._alias = "sinhala_rec"
        self._mci_send("close %s" % self._alias)
        err, _ = self._mci_send("open new type waveaudio alias %s" % self._alias)
        if err:
            raise RecorderError("Cannot open the microphone: " + self._mci_error(err))
        self._mci_send("set %s time format ms" % self._alias)
        err, _ = self._mci_send("record %s" % self._alias)
        if err:
            msg = self._mci_error(err)
            self._mci_send("close %s" % self._alias)
            raise RecorderError("Cannot start recording: " + msg)

    def _stop_mci(self):
        self._mci_send("stop %s" % self._alias)
        path = _new_wav_path()
        err, _ = self._mci_send('save %s "%s"' % (self._alias, path))
        self._mci_send("close %s" % self._alias)
        if err:
            try:
                os.remove(path)
            except OSError:
                pass
            raise RecorderError("Cannot save the recording: " + self._mci_error(err))
        return path
