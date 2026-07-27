# -*- coding: utf-8 -*-
"""
voice_button.py — a floating circular mic button with a pulsing glow ring.

Three visual states:
  * idle       — subtle circular mic button
  * recording  — animated concentric glow rings (breathing) + red tint
  * busy       — ⏳ while the audio is being transcribed

The glow is drawn on a tk.Canvas whose background matches the text box behind it,
so the rings blend softly instead of showing a square patch.
"""

import math
import tkinter as tk

import customtkinter as ctk

from .widgets import font, sinhala_family  # noqa: F401  (font used for glyph)


def _rgb(widget, color):
    r, g, b = widget.winfo_rgb(color)
    return (r // 256, g // 256, b // 256)


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _blend(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class VoiceButton(ctk.CTkFrame):
    def __init__(self, master, command, size=92, glow="#ff4d4d",
                 idle_fg=("#e7ecf5", "#2b3446"), idle_hover=("#dbe3f1", "#354056"),
                 rec_fg="#ef4444", rec_hover="#dc2626", **kw):
        super().__init__(master, fg_color="transparent", width=size, height=size, **kw)
        self.command = command
        self.size = size
        self.glow = glow
        self.idle_fg = idle_fg
        self.idle_hover = idle_hover
        self.rec_fg = rec_fg
        self.rec_hover = rec_hover
        self._mode = "idle"
        self._anim = None
        self._phase = 0.0

        self._bg = self._textbox_bg()
        self.canvas = tk.Canvas(self, width=size, height=size, bg=self._bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()

        d = 54
        self.btn = ctk.CTkButton(
            self.canvas, text="🎤", width=d, height=d, corner_radius=d // 2,
            fg_color=idle_fg, hover_color=idle_hover, bg_color=self._bg,
            text_color=("#1f2733", "#e8edf4"), font=(sinhala_family(), 20),
            command=self._clicked,
        )
        self._win = self.canvas.create_window(size // 2, size // 2, window=self.btn)
        self._bg_rgb = _rgb(self.canvas, self._bg)
        self._glow_rgb = _rgb(self.canvas, self.glow)

    # ----- appearance ----------------------------------------------------
    @staticmethod
    def _textbox_bg():
        try:
            col = ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]
            return col[0] if ctk.get_appearance_mode() == "Light" else col[1]
        except Exception:
            return "#1a1f28" if ctk.get_appearance_mode() == "Dark" else "#ffffff"

    def refresh_theme(self):
        """Re-blend to the current theme's text-box background."""
        self._bg = self._textbox_bg()
        self._bg_rgb = _rgb(self.canvas, self._bg)
        self._glow_rgb = _rgb(self.canvas, self.glow)
        self.canvas.configure(bg=self._bg)
        try:
            self.btn.configure(bg_color=self._bg)
        except Exception:
            pass

    def _clicked(self):
        if self._mode != "busy" and self.command:
            self.command()

    # ----- states --------------------------------------------------------
    def set_recording(self, on):
        if on:
            self._mode = "recording"
            self.btn.configure(text="🎤", fg_color=self.rec_fg, hover_color=self.rec_hover,
                               text_color="white", state="normal")
            self._start_anim()
        else:
            self._mode = "idle"
            self._stop_anim()
            self.btn.configure(text="🎤", fg_color=self.idle_fg, hover_color=self.idle_hover,
                               text_color=("#1f2733", "#e8edf4"), state="normal")

    def set_busy(self, on):
        if on:
            self._mode = "busy"
            self._stop_anim()
            self.btn.configure(text="⏳", state="disabled")
        else:
            self.set_recording(False)

    # ----- glow animation ------------------------------------------------
    def _start_anim(self):
        if self._anim is None:
            self._phase = 0.0
            self._pulse()

    def _stop_anim(self):
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None
        self.canvas.delete("glow")

    def _pulse(self):
        if self._mode != "recording":
            self._anim = None
            return
        self.canvas.delete("glow")
        c = self.size / 2
        base = 30
        rings = 3
        for i in range(rings):
            ph = self._phase + i * (2 * math.pi / rings)
            s = (math.sin(ph) + 1) / 2                     # 0..1 breathing
            r = base + 4 + s * 16 + i * 3
            intensity = max(0.0, 0.6 * (1 - s))            # fade as it expands
            col = _hex(_blend(self._bg_rgb, self._glow_rgb, intensity))
            self.canvas.create_oval(c - r, c - r, c + r, c + r,
                                    outline=col, width=3, tags="glow")
        self.canvas.tag_lower("glow", self._win)           # keep rings behind the button
        self._phase = (self._phase + 0.14) % (2 * math.pi)
        self._anim = self.after(55, self._pulse)

    def destroy(self):
        self._stop_anim()
        super().destroy()
