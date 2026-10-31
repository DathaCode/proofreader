# -*- coding: utf-8 -*-
"""
voice_button.py — the voice-typing button (v5).

A smooth pill button that sits next to "Check":

    idle        [ 🎙  Voice ]                      neutral pill
    recording   [ ■  0:07 ] ▂▅▇▃▁                  red pill + live mic-level bars
    busy        [ 🎙  Converting… ]                 disabled

Icons are drawn with Pillow at 4x and scaled down (anti-aliased) — the v4 button
drew on a plain Tk canvas, which cannot anti-alias, so its circles looked jagged.
The level bars follow the real microphone level (MicRecorder.level), so users can
see that the mic is actually hearing them.

Interface kept from v4: VoiceButton(master, command), set_recording(bool),
set_busy(bool), refresh_theme(); plus retranslate().
"""

import math
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import theme as TH

_RED, _RED_HOVER = "#ef4444", "#dc2626"
_LABELS = {"voice_btn": "Voice", "voice_busy": "Converting…"}


def _icon(kind, color, size=18, scale=4):
    """Anti-aliased mic / stop icon as a PIL image."""
    S = size * scale
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, int(S * 0.09))
    if kind == "stop":
        a, b = int(S * 0.27), int(S * 0.73)
        d.rounded_rectangle((a, a, b, b), radius=int(S * 0.09), fill=color)
    else:  # mic
        d.rounded_rectangle((int(S * .35), int(S * .06), int(S * .65), int(S * .60)),
                            radius=int(S * .15), fill=color)
        d.arc((int(S * .20), int(S * .24), int(S * .80), int(S * .76)),
              start=0, end=180, fill=color, width=w)
        d.line((S // 2, int(S * .76), S // 2, int(S * .90)), fill=color, width=w)
        d.line((int(S * .32), int(S * .91), int(S * .68), int(S * .91)), fill=color, width=w)
    return img.resize((size, size), Image.LANCZOS)


def _ctk_icon(kind, light, dark, size=18):
    return ctk.CTkImage(light_image=_icon(kind, light, size), dark_image=_icon(kind, dark, size),
                        size=(size, size))


class VoiceButton(ctk.CTkFrame):
    BARS = 5
    PROFILE = (0.55, 0.85, 1.0, 0.8, 0.5)     # middle bars move most

    def __init__(self, master, command, level_fn=None, t=None, height=42, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.command = command
        self.level_fn = level_fn or (lambda: 0.0)
        self._t = t or (lambda key, *a: _LABELS.get(key, key))
        self._mode = "idle"                    # idle | recording | busy
        self._started = 0.0
        self._job = None
        self._levels = [0.0] * self.BARS
        self._phase = 0.0

        self._img_mic = _ctk_icon("mic", "#1f2733", "#e8edf4")
        self._img_mic_muted = _ctk_icon("mic", "#8a94a6", "#7d889a")
        self._img_stop = _ctk_icon("stop", "#ffffff", "#ffffff")

        self.btn = ctk.CTkButton(self, text="", height=height, corner_radius=height // 2,
                                 width=118, compound="left", border_spacing=10,
                                 command=self._clicked)
        self.btn.pack(side="left")
        self.meter = tk.Canvas(self, width=self.BARS * 8, height=26, highlightthickness=0, bd=0)
        self.refresh_theme()

    # ----- public --------------------------------------------------------
    def set_recording(self, on):
        if on:
            self._mode = "recording"
            self._started = time.time()
            self._levels = [0.0] * self.BARS
            self.meter.pack(side="left", padx=(10, 0))
            self._tick()
        else:
            self._mode = "idle"
            self._stop()
        self._render()

    def set_busy(self, on):
        self._mode = "busy" if on else "idle"
        self._stop()
        self._render()

    def refresh_theme(self):
        bg = TH.CARD_BG[1] if ctk.get_appearance_mode() == "Dark" else TH.CARD_BG[0]
        self.meter.configure(bg=bg)
        self._render()

    def retranslate(self):
        self._render()

    # ----- internals -----------------------------------------------------
    def _clicked(self):
        if self._mode != "busy" and self.command:
            self.command()

    def _stop(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.meter.pack_forget()

    def _render(self):
        font = (_ui_font(), 13, "bold")
        if self._mode == "recording":
            secs = int(time.time() - self._started)
            self.btn.configure(text="%d:%02d" % (secs // 60, secs % 60), image=self._img_stop,
                               fg_color=_RED, hover_color=_RED_HOVER, text_color="#ffffff",
                               state="normal", font=font)
        elif self._mode == "busy":
            self.btn.configure(text=self._t("voice_busy"), image=self._img_mic_muted,
                               fg_color=TH.NEUTRAL, hover_color=TH.NEUTRAL, text_color=TH.MUTED,
                               state="disabled", font=font)
        else:
            self.btn.configure(text=self._t("voice_btn"), image=self._img_mic,
                               fg_color=TH.NEUTRAL, hover_color=TH.NEUTRAL_HOVER,
                               text_color=TH.TEXT, state="normal", font=font)

    def _tick(self):
        if self._mode != "recording":
            self._job = None
            return
        self._phase += 0.35
        level = max(0.0, min(1.0, float(self.level_fn() or 0.0)))
        # Natural-looking motion: real level, shaped per bar, with a little
        # movement even in silence so the user can see it is listening.
        for i in range(self.BARS):
            wobble = 0.08 * (1 + math.sin(self._phase + i * 1.3))
            target = min(1.0, level * self.PROFILE[i] * 1.4 + wobble)
            self._levels[i] = 0.55 * self._levels[i] + 0.45 * target
        cv = self.meter
        cv.delete("all")
        h = int(cv.cget("height"))
        for i, lv in enumerate(self._levels):
            bh = max(4, int(lv * (h - 2)))
            x = i * 8 + 2
            y0 = (h - bh) // 2
            cv.create_rectangle(x, y0, x + 4, y0 + bh, fill=_RED, outline=_RED)
        self._render()
        self._job = self.after(70, self._tick)

    def destroy(self):
        self._stop()
        super().destroy()


def _ui_font():
    from .widgets import ui_family
    return ui_family()
