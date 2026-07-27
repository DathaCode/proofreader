# -*- coding: utf-8 -*-
"""
voice_button.py — a floating circular mic button with a pulsing glow ring.

Everything is drawn on a single tk.Canvas (face circle + vector mic icon + glow),
and the click is a plain canvas <Button-1> binding — which fires reliably (unlike
a CTk button embedded via create_window). States: idle / recording / busy.
"""

import math
import tkinter as tk

import customtkinter as ctk


def _rgb(widget, color):
    r, g, b = widget.winfo_rgb(color)
    return (r // 256, g // 256, b // 256)


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _blend(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class VoiceButton(ctk.CTkFrame):
    def __init__(self, master, command, size=80, glow="#ff4d4d", **kw):
        super().__init__(master, fg_color="transparent", width=size, height=size, **kw)
        self.command = command
        self.size = size
        self.glow = glow
        self._mode = "idle"      # idle | recording | busy
        self._hover = False
        self._anim = None
        self._phase = 0.0

        self._bg = self._textbox_bg()
        self.canvas = tk.Canvas(self, width=size, height=size, bg=self._bg,
                                highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

        self._bg_rgb = _rgb(self.canvas, self._bg)
        self._glow_rgb = _rgb(self.canvas, self.glow)
        self._render()

    # ----- theme ---------------------------------------------------------
    @staticmethod
    def _textbox_bg():
        try:
            col = ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]
            return col[0] if ctk.get_appearance_mode() == "Light" else col[1]
        except Exception:
            return "#1a1f28" if ctk.get_appearance_mode() == "Dark" else "#ffffff"

    def refresh_theme(self):
        self._bg = self._textbox_bg()
        self._bg_rgb = _rgb(self.canvas, self._bg)
        self._glow_rgb = _rgb(self.canvas, self.glow)
        self.canvas.configure(bg=self._bg)
        self._render()

    # ----- events --------------------------------------------------------
    def _on_click(self, _e=None):
        if self._mode != "busy" and self.command:
            self.command()

    def _on_enter(self, _e=None):
        self._hover = True
        self._render()

    def _on_leave(self, _e=None):
        self._hover = False
        self._render()

    # ----- states --------------------------------------------------------
    def set_recording(self, on):
        self._mode = "recording" if on else "idle"
        if on:
            self._start_anim()
        else:
            self._stop_anim()
        self._render()

    def set_busy(self, on):
        if on:
            self._mode = "busy"
            self._stop_anim()
        else:
            self._mode = "idle"
        self._render()

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

    def _pulse(self):
        if self._mode != "recording":
            self._anim = None
            return
        self._phase = (self._phase + 0.14) % (2 * math.pi)
        self._render()
        self._anim = self.after(55, self._pulse)

    # ----- drawing -------------------------------------------------------
    def _face_colors(self):
        """(circle fill, mic stroke) for the current mode + hover."""
        dark = ctk.get_appearance_mode() == "Dark"
        if self._mode == "recording":
            return ("#ef4444" if not self._hover else "#f05252"), "#ffffff"
        if self._mode == "busy":
            return ("#39445a" if dark else "#d7deea"), ("#9aa6b6" if dark else "#8a94a6")
        # idle
        if dark:
            fill = "#333f54" if self._hover else "#2b3446"
            return fill, "#e8edf4"
        fill = "#dbe3f1" if self._hover else "#e7ecf5"
        return fill, "#1f2733"

    def _render(self):
        cv = self.canvas
        cv.delete("all")
        c = self.size / 2

        if self._mode == "recording":
            for i in range(3):
                ph = self._phase + i * (2 * math.pi / 3)
                s = (math.sin(ph) + 1) / 2
                r = 20 + 3 + s * 10 + i * 2
                intensity = max(0.0, 0.6 * (1 - s))
                col = _hex(_blend(self._bg_rgb, self._glow_rgb, intensity))
                cv.create_oval(c - r, c - r, c + r, c + r, outline=col, width=2)

        fill, stroke = self._face_colors()
        rad = 20
        cv.create_oval(c - rad, c - rad, c + rad, c + rad, fill=fill, outline=fill)
        self._draw_mic(c, c, stroke)

    def _draw_mic(self, cx, cy, color):
        """Small vector mic icon (capsule body + cradle + stand)."""
        w = 2
        bw, top, bot = 5, cy - 12, cy - 1          # capsule body
        self.canvas.create_arc(cx - bw, top - bw, cx + bw, top + bw,
                               start=0, extent=180, style="arc", outline=color, width=w)
        self.canvas.create_arc(cx - bw, bot - bw, cx + bw, bot + bw,
                               start=180, extent=180, style="arc", outline=color, width=w)
        self.canvas.create_line(cx - bw, top, cx - bw, bot, fill=color, width=w)
        self.canvas.create_line(cx + bw, top, cx + bw, bot, fill=color, width=w)
        # cradle (U hugging the mic bottom)
        self.canvas.create_arc(cx - 9, cy - 8, cx + 9, cy + 10,
                               start=200, extent=140, style="arc", outline=color, width=w)
        # stand + base
        self.canvas.create_line(cx, cy + 10, cx, cy + 15, fill=color, width=w)
        self.canvas.create_line(cx - 6, cy + 16, cx + 6, cy + 16, fill=color, width=w,
                               capstyle="round")

    def destroy(self):
        self._stop_anim()
        super().destroy()
