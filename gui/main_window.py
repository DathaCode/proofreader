# -*- coding: utf-8 -*-
"""
main_window.py — the Sinhala Proofreader main application window (v5).

Layout
  header   brand · connection pill · History · theme · Settings
  banner   (only when needed) Control PC offline / update available / errors
  body     [ Your text ]                 [ Highlighted | Corrected ]
           editor + voice + word counter  results view + Copy / Use / Teach / Export
  issues   one row per issue with Accept / Ignore (+ Accept all)
  status   last action · stats

Accepting an issue edits your text in place instantly — no new Gemini call.
In LAN mode the app checks in with the Control PC every 30 s, so the window
always shows whether the proxy is reachable, and long texts up to the proxy's
word limit are checked in parallel parts.
"""

import os
import sys
import time
import threading
import datetime
import unicodedata

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from engine.proofreader import SinhalaProofreader
from .widgets import (font, text_font, sinhala_family, Pill, Banner, IssueRow, SinhalaText,
                      segment_text, editor_colors, clipboard_text)
from .settings_dialog import SettingsDialog
from .welcome_dialog import WelcomeDialog
from .voice_button import VoiceButton
from .history import History
from .i18n import t
from . import theme as TH

try:
    from version import __version__ as _APP_VER
except Exception:
    _APP_VER = "5.0"

APP_TITLE_EN = "Sinhala Proofreader"
VERSION = "v" + _APP_VER
HEARTBEAT_SECONDS = 30
FONT_MIN, FONT_MAX = 12, 28


def _resource_path(*parts):
    """Resolve a bundled resource both in dev and inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _vtuple(v):
    out = []
    for p in (v or "").split("."):
        try:
            out.append(int(p))
        except ValueError:
            break
    return tuple(out)


def _fmt(n):
    return "{:,}".format(int(n))


def _norm(text):
    return unicodedata.normalize("NFC", (text or "").strip())


def _joins(ch):
    """True for marks that belong to the previous letter (vowel signs, al-lakuna,
    ZWJ/ZWNJ): a highlight must never start or end in front of one."""
    return unicodedata.category(ch) in ("Mn", "Mc") or ch in "‌‍"


def _visual_span(text, s, e):
    """Widen [s, e) to whole letters for DISPLAY only. An issue can cover part of a
    word (e.g. "ලන්කාව" inside "ලන්කාවේ"); splitting a tag before the vowel sign
    makes Windows draw it on a dotted circle. Replacement still uses [s, e)."""
    n = len(text)
    while s > 0 and (_joins(text[s]) or text[s - 1] == "‍"):
        s -= 1
    while e < n and (_joins(text[e]) or text[e - 1] == "‍"):
        e += 1
    return s, e


class MainWindow(ctk.CTk):
    def __init__(self, config):
        super().__init__()
        self.config_obj = config
        self.proofreader = SinhalaProofreader(config)
        self.history = History()
        self._tr = []                 # [(widget, key)] for live language switching
        self._result = None           # last successful result
        self._work_text = ""          # checked text with accepted fixes applied
        self._issues = []             # issues still open (positions in _work_text)
        self._focused = None          # issue highlighted in the results view
        self._last_corrected_text = ""
        self._recorder = None         # lazy MicRecorder for voice typing
        self._recording = False
        self._checking = False
        self._check_started = 0.0
        self._online = None           # None = unknown, True / False after a heartbeat
        self._update_dismissed = False
        self._font_size = int(config.get("font_size", 16) or 16)
        self._beat_now = threading.Event()
        self._closing = False

        ctk.set_appearance_mode(config.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self.title("%s  —  %s" % (APP_TITLE_EN, VERSION))
        self.geometry(self._safe_geometry(config.get("window_geometry")))
        self.minsize(1100, 720)
        self.configure(fg_color=TH.WINDOW_BG)
        self._set_app_icon()

        self._build_header()
        self.banner = Banner(self, pack_opts={"fill": "x", "padx": 16, "pady": (10, 0),
                                              "after": self._header_accent})
        self.update_banner = Banner(self, pack_opts={"fill": "x", "padx": 16, "pady": (10, 0),
                                                     "after": self._header_accent})
        self._build_statusbar()
        self._build_issues()
        self._build_body()

        self.bind("<Control-Return>", lambda _e: self.on_check())
        self.bind("<Control-l>", lambda _e: self.on_clear())
        self.bind("<Control-L>", lambda _e: self.on_clear())
        self.bind("<Control-Shift-C>", lambda _e: (self.on_copy(), "break")[1])
        self.bind("<Control-Shift-H>", lambda _e: self.open_history())
        self.bind("<Control-equal>", lambda _e: self.change_font(+1))
        self.bind("<Control-plus>", lambda _e: self.change_font(+1))
        self.bind("<Control-minus>", lambda _e: self.change_font(-1))
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._refresh_mode_ui()
        self._show_issues_placeholder("issues_start")
        self._update_counts()
        if config.get("window_zoomed"):
            self.after(80, lambda: self.state("zoomed"))

        if self.config_obj.get("connection_mode", "direct") == "lan_proxy":
            threading.Thread(target=self.proofreader.sync_corrections_from_proxy,
                             daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        if (self.config_obj.get("connection_mode", "direct") == "direct"
                and not self.config_obj.has_api_key()):
            self.after(300, self._show_welcome)

    def _safe_geometry(self, geo):
        """Remembered "WxH+X+Y", unless it would open off-screen (monitor changed)."""
        import re as _re
        m = _re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", geo or "")
        if not m:
            return "1320x860"
        w, h, x, y = (int(g) for g in m.groups())
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x < -50 or y < -20 or x > sw - 200 or y > sh - 150 or w > sw + 50:
            return "%dx%d" % (min(w, sw), min(h, sh))
        return geo

    def _set_app_icon(self):
        """Window / taskbar icon from assets/ (multi-size .ico on Windows; the .png
        is also the inherited default so child windows share it)."""
        ico = _resource_path("assets", "icon.ico")
        png = _resource_path("assets", "icon.png")
        try:
            if os.path.exists(png):
                self._icon_image = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_image)
        except Exception:
            pass
        try:
            if os.name == "nt" and os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ================================================================ build
    def _card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=TH.CARD_BG, corner_radius=TH.R_CARD,
                            border_width=1, border_color=TH.BORDER, **kw)

    def _btn(self, parent, key=None, style="secondary", command=None, reg=True, **kw):
        """Styled button. `key` = i18n text; reg=False for short-lived popups
        (they must not be kept in the live-retranslate registry)."""
        colors = {
            "primary": dict(fg_color=TH.ACCENT, hover_color=TH.ACCENT_HOVER, text_color="#ffffff"),
            "success": dict(fg_color=TH.SUCCESS, hover_color=TH.SUCCESS_HOVER, text_color="#ffffff"),
            "secondary": dict(fg_color=TH.NEUTRAL, hover_color=TH.NEUTRAL_HOVER, text_color=TH.TEXT),
            "ghost": dict(fg_color="transparent", hover_color=TH.NEUTRAL_HOVER, text_color=TH.TEXT,
                          border_width=1, border_color=TH.BORDER),
        }[style]
        kw.setdefault("height", 34)
        kw.setdefault("font", font(13, style in ("primary", "success")))
        if key and not reg:
            kw["text"] = self._t(key)
        b = ctk.CTkButton(parent, corner_radius=TH.R_BTN, command=command, **dict(colors, **kw))
        return self._reg(b, key) if (key and reg) else b

    def _build_header(self):
        header = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=TH.HEADER_BG)
        header.pack(fill="x")
        header.pack_propagate(False)
        self._header_accent = ctk.CTkFrame(self, height=2, corner_radius=0, fg_color=TH.ACCENT)
        self._header_accent.pack(fill="x")

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", padx=18)
        ctk.CTkLabel(brand, text="අ", width=40, height=40, corner_radius=10,
                     fg_color=TH.ACCENT, text_color="#ffffff",
                     font=(sinhala_family(), 20, "bold")).pack(side="left", padx=(0, 12))
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        self._reg(ctk.CTkLabel(titles, font=font(18, True), text_color=TH.TEXT, anchor="w"),
                  "app_title").pack(anchor="w")
        self._reg(ctk.CTkLabel(titles, font=font(12), text_color=TH.MUTED, anchor="w"),
                  "app_subtitle").pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=18)
        self._btn(right, "settings_btn", "primary", self.open_settings, width=118).pack(
            side="right", padx=(8, 0))
        self.theme_switch = ctk.CTkSwitch(right, text="", command=self._toggle_theme,
                                          progress_color=TH.ACCENT, width=46)
        self.theme_switch.pack(side="right", padx=(8, 4))
        self._theme_label = ctk.CTkLabel(right, text="", font=font(12), text_color=TH.MUTED)
        self._theme_label.pack(side="right")
        self._sync_theme_switch()
        self._btn(right, "history_btn", "ghost", self.open_history, width=96).pack(
            side="right", padx=(8, 12))
        self.conn_pill = Pill(right)
        self.conn_pill.pack(side="right")

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")
        body.grid_rowconfigure(0, weight=1)
        self._build_input_panel(body)
        self._build_results_panel(body)

    def _build_input_panel(self, parent):
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self._reg(ctk.CTkLabel(head, font=font(15, True), text_color=TH.TEXT), "your_text").pack(side="left")
        self._btn(head, "clear_btn2", "ghost", self.on_clear, width=70, height=30,
                  font=font(12)).pack(side="right")
        self._btn(head, "paste_btn", "ghost", self.on_paste, width=70, height=30,
                  font=font(12)).pack(side="right", padx=(0, 6))
        self._btn(head, None, "ghost", lambda: self.change_font(+1), text="A+", width=36,
                  height=30, font=font(12, True)).pack(side="right", padx=(0, 10))
        self._btn(head, None, "ghost", lambda: self.change_font(-1), text="A−", width=36,
                  height=30, font=font(11, True)).pack(side="right", padx=(0, 4))

        # SinhalaText = fast tk.Text for long Sinhala paragraphs (see widgets.py).
        self.input_view = SinhalaText(card, font_spec=text_font(self._font_size))
        self.input_view.grid(row=1, column=0, sticky="nsew", padx=14, pady=0)
        self.input_box = self.input_view.text
        # add="+": keep SinhalaText's own re-segmenting bindings.
        self.input_box.bind("<KeyRelease>", self._update_counts, add="+")
        self.input_view.after_paste = self._update_counts

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 14))
        meter = ctk.CTkFrame(foot, fg_color="transparent")
        meter.pack(side="left", fill="x", expand=True)
        self.count_label = ctk.CTkLabel(meter, text="", anchor="w", font=font(12),
                                        text_color=TH.MUTED)
        self.count_label.pack(anchor="w")
        self.limit_bar = ctk.CTkProgressBar(meter, height=6, width=200, corner_radius=3,
                                            progress_color=TH.ACCENT)
        self.limit_bar.set(0)
        self.limit_bar.pack(anchor="w", pady=(3, 0))
        self.check_btn = self._btn(foot, "check_btn2", "primary", self.on_check,
                                   width=210, height=42, font=font(14, True))
        self.check_btn.pack(side="right")
        # Voice typing: pill next to Check; shows a timer + live mic level while recording.
        self.voice_btn = VoiceButton(foot, command=self.on_mic, t=self._t,
                                     level_fn=lambda: getattr(self._recorder, "level", 0.0))
        self.voice_btn.pack(side="right", padx=(0, 10))

    def _build_results_panel(self, parent):
        card = self._card(parent)
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self.view_tabs = ctk.CTkSegmentedButton(head, values=["a", "b"], height=32,
                                                font=font(13, True),
                                                command=self._on_tab)
        self.view_tabs.pack(side="left")
        self.summary_pill = Pill(head)

        self.progress_row = ctk.CTkFrame(card, fg_color="transparent")
        self.progress = ctk.CTkProgressBar(self.progress_row, mode="indeterminate", height=4,
                                           progress_color=TH.ACCENT)
        self.progress.pack(fill="x")
        self.progress_label = ctk.CTkLabel(self.progress_row, text="", font=font(12),
                                           text_color=TH.MUTED, anchor="w")
        self.progress_label.pack(anchor="w", pady=(4, 0))

        self.view_stack = ctk.CTkFrame(card, fg_color="transparent")
        self.view_stack.grid(row=2, column=0, sticky="nsew", padx=14)
        self.view_stack.grid_rowconfigure(0, weight=1)
        self.view_stack.grid_columnconfigure(0, weight=1)

        # Highlighted view: read-only, tag-based highlights.
        self.hl_frame = SinhalaText(self.view_stack, readonly=True)
        self.result_text = self.hl_frame.text
        self.result_text.configure(cursor="arrow", state="disabled")
        for tag in ("spell_error", "grammar_error"):
            self.result_text.tag_bind(tag, "<Button-1>", self._on_highlight_click)
            self.result_text.tag_bind(tag, "<Enter>", lambda _e: self.result_text.configure(cursor="hand2"))
            self.result_text.tag_bind(tag, "<Leave>", lambda _e: self.result_text.configure(cursor="arrow"))

        # Corrected view: editable, so users can adjust and "Teach".
        self.corrected_view = SinhalaText(self.view_stack, font_spec=text_font(self._font_size))
        self.corrected_box = self.corrected_view.text

        self.view_hint = ctk.CTkLabel(card, text="", anchor="w", font=font(12),
                                      text_color=TH.MUTED)
        self.view_hint.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 0))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=14, pady=(8, 14))
        self.copy_btn = self._btn(actions, "copy_corrected", "primary", self.on_copy, height=38)
        self.copy_btn.pack(side="left")
        self._btn(actions, "use_corrected", "secondary", self.use_corrected,
                  height=38).pack(side="left", padx=(8, 0))
        self._btn(actions, "export_btn2", "ghost", self.on_export, height=38,
                  width=80).pack(side="right")
        self._btn(actions, "teach_btn", "ghost", self.submit_manual_corrections, height=38,
                  width=96).pack(side="right", padx=(0, 8))

        self._style_result_text()
        self._set_tabs()
        self._show_view("highlight")

    def _build_issues(self):
        card = self._card(self)
        card.pack(side="bottom", fill="x", padx=16, pady=(10, 10))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        self._reg(ctk.CTkLabel(head, font=font(15, True), text_color=TH.TEXT),
                  "issues_label").pack(side="left")
        self.spell_pill = Pill(head)
        self.grammar_pill = Pill(head)
        self.accept_all_btn = self._btn(head, None, "success", self.accept_all, height=30,
                                        font=font(12, True), text="")
        self.issues_frame = ctk.CTkScrollableFrame(card, height=170, fg_color="transparent")
        self.issues_frame.pack(fill="x", padx=8, pady=(0, 10))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color=TH.BAR_BG)
        bar.pack(fill="x", side="bottom")
        self.status_label = ctk.CTkLabel(bar, text=self._t("ready"), anchor="w",
                                         font=font(12), text_color=TH.MUTED)
        self.status_label.pack(side="left", padx=16)
        ctk.CTkLabel(bar, text=VERSION, font=font(11), text_color=TH.MUTED).pack(side="right", padx=16)
        self.stats_label = ctk.CTkLabel(bar, text="", anchor="e", font=font(12),
                                        text_color=TH.MUTED)
        self.stats_label.pack(side="right", padx=4)

    # ============================================================== views
    def _set_tabs(self):
        self._tab_names = {"highlight": self._t("tab_highlight"),
                           "corrected": self._t("tab_corrected")}
        current = getattr(self, "_view", "highlight")
        self.view_tabs.configure(values=list(self._tab_names.values()))
        self.view_tabs.set(self._tab_names[current])

    def _on_tab(self, value):
        for key, name in self._tab_names.items():
            if name == value:
                self._show_view(key)

    def _show_view(self, key):
        self._view = key
        if key == "highlight":
            self.corrected_view.grid_forget()
            self.hl_frame.grid(row=0, column=0, sticky="nsew")
            self.view_hint.configure(text=self._t("hint_highlight"))
        else:
            self.hl_frame.grid_forget()
            self.corrected_view.grid(row=0, column=0, sticky="nsew")
            self.view_hint.configure(text=self._t("hint_corrected"))
        self.view_tabs.set(self._tab_names[key])

    def _style_result_text(self):
        c = TH.result_colors()
        size = self._font_size
        fam = sinhala_family()
        for view in (self.hl_frame, getattr(self, "input_view", None),
                     getattr(self, "corrected_view", None)):
            if view is not None:
                view.refresh_theme()
        self.result_text.configure(font=(fam, size))
        self.result_text.tag_configure("spell_error", background=c["spell_bg"],
                                       foreground=c["spell_fg"], underline=True,
                                       font=(fam, size, "bold"))
        self.result_text.tag_configure("grammar_error", background=c["grammar_bg"],
                                       foreground=c["grammar_fg"], underline=True,
                                       font=(fam, size))
        self.result_text.tag_configure("focus", background=c["focus_bg"], foreground=c["focus_fg"])
        self.result_text.tag_raise("focus")
        if getattr(self, "voice_btn", None) is not None:
            self.voice_btn.refresh_theme()

    def change_font(self, delta):
        new = max(FONT_MIN, min(FONT_MAX, self._font_size + delta))
        if new == self._font_size:
            return
        self._font_size = new
        self.input_box.configure(font=text_font(new))
        self.corrected_box.configure(font=text_font(new))
        self._style_result_text()
        self.config_obj.set("font_size", new)
        self.config_obj.save()

    def _on_resize(self, event):
        if event.widget is self:
            w = self.winfo_width()
            for b in (self.banner, self.update_banner):
                b.wrap(w)
            for row in self.issues_frame.winfo_children():
                if isinstance(row, IssueRow):
                    row.set_wrap(w)

    # ===================================================== word counter
    def _update_counts(self, _e=None):
        text = self.input_box.get("1.0", "end-1c")
        words = len(text.split())
        limit = self.proofreader.max_words
        if limit:
            self.count_label.configure(text=self._t("words_limit", _fmt(words), _fmt(limit)))
            ratio = min(1.0, words / float(limit))
            self.limit_bar.set(ratio)
            color = TH.DANGER if words > limit else (TH.WARNING if ratio > 0.9 else TH.ACCENT)
            self.limit_bar.configure(progress_color=color)
            self.count_label.configure(text_color=TH.DANGER_TEXT if words > limit else TH.MUTED)
            if not self.limit_bar.winfo_ismapped():
                self.limit_bar.pack(anchor="w", pady=(3, 0))
        else:
            self.count_label.configure(text=self._t("words_count", _fmt(words)), text_color=TH.MUTED)
            self.limit_bar.pack_forget()

    # ================================================== connection state
    def _heartbeat_loop(self):
        """Background: check in with the Control PC every 30 s (LAN mode)."""
        while not self._closing:
            try:
                ok, info = self.proofreader.heartbeat()
            except Exception as exc:          # never let the loop die
                ok, info = False, str(exc)
            if self._closing:
                return
            try:
                self.after(0, lambda o=ok, i=info: self._on_heartbeat(o, i))
            except RuntimeError:              # window already destroyed
                return
            self._beat_now.wait(HEARTBEAT_SECONDS)
            self._beat_now.clear()

    def beat_now(self):
        self._beat_now.set()

    def _on_heartbeat(self, ok, info):
        if self.config_obj.get("connection_mode", "direct") != "lan_proxy":
            return
        url = self.config_obj.get("proxy_url", "")
        if ok:
            name = info.get("server_name") or url.replace("http://", "")
            self.conn_pill.set("ok" if info.get("model_ready", True) else "warn",
                               self._t("conn_ok", name))
            if self._online is False:
                self._set_status(self._t("reconnected"))
            if self.banner.kind == "danger":
                self.banner.hide()
            self._online = True
            self._update_counts()
            self._maybe_show_update(info)
        else:
            self.conn_pill.set("bad", self._t("conn_offline"))
            self._online = False
            self.banner.show("danger", self._t("offline_banner", url.replace("http://", "")),
                             self._t("retry_now"), self._retry_connection, closable=False)
            self.banner.wrap(self.winfo_width())

    def _retry_connection(self):
        self.conn_pill.set("neutral", self._t("conn_wait"))
        self.beat_now()

    def _maybe_show_update(self, info):
        latest = info.get("client_latest_version", "")
        if (latest and not self._update_dismissed
                and _vtuple(_APP_VER) < _vtuple(latest)):
            self.update_banner.show("warn", self._t("update_banner", latest,
                                                    info.get("client_update_note", "")),
                                    self._t("dismiss"), self._dismiss_update, closable=False)
            self.update_banner.wrap(self.winfo_width())

    def _dismiss_update(self):
        self._update_dismissed = True
        self.update_banner.hide()

    def _refresh_mode_ui(self):
        mode = self.config_obj.get("connection_mode", "direct")
        if mode == "lan_proxy":
            if self._online is None:
                self.conn_pill.set("neutral", self._t("conn_wait"))
        else:
            self.banner.hide()
            self.update_banner.hide()
            if self.config_obj.has_api_key():
                self.conn_pill.set("info", self._t("conn_direct",
                                   self.config_obj.get("gemini_model", "gemini-2.5-flash")))
            else:
                self.conn_pill.set("bad", self._t("conn_nokey"))
        self._update_counts()

    # =========================================================== voice typing
    def on_mic(self):
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        # Immediate acknowledgement that the click registered — glow + pill +
        # status show at once, BEFORE we touch the mic device.
        self._recording = True
        self.voice_btn.set_recording(True)
        self._show_recording(True)
        self._set_status(self._t("mic_recording"))
        self.update_idletasks()
        try:
            from engine.audio_recorder import MicRecorder
            if self._recorder is None:
                self._recorder = MicRecorder()
            if not self._recorder.available:
                raise RuntimeError(self._t("mic_unavailable"))
            self._recorder.start()
        except Exception as exc:
            self._reset_mic()
            self._set_status(self._t("mic_failed", str(exc)[:90]))
            messagebox.showerror("Voice", "Voice failed: %s" % str(exc)[:220])

    def _stop_recording(self):
        self._recording = False
        self._show_recording(False)
        self.voice_btn.set_busy(True)
        try:
            path = self._recorder.stop()
        except Exception as exc:
            self._reset_mic()
            self._set_status(self._t("mic_failed", str(exc)[:70]))
            return
        if not path:
            self._reset_mic()
            return
        self._set_status(self._t("mic_converting"))
        threading.Thread(target=self._transcribe_worker, args=(path,), daemon=True).start()

    def _reset_mic(self):
        self._recording = False
        self._show_recording(False)
        self.voice_btn.set_recording(False)  # clears busy/recording -> idle

    def _show_recording(self, show):
        """The voice button itself shows recording state (timer + level bars)."""

    def _transcribe_worker(self, path):
        text, err = None, None
        try:
            text = self.proofreader.transcribe(
                path, on_progress=lambda m: self.after(0, lambda: self._set_status(m)))
        except Exception as exc:  # GeminiError or any failure
            err = exc
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        self.after(0, lambda: self._transcribe_done(text, err))

    def _transcribe_done(self, text, err):
        self._reset_mic()
        if err is not None:
            msg = getattr(err, "message_en", None) or str(err)
            self._set_status(self._t("mic_failed", msg[:90]))
            messagebox.showerror("Voice", "Voice failed: %s" % msg[:220])
            return
        text = (text or "").strip()
        if not text:
            self._set_status(self._t("mic_empty"))
            return
        current = self.input_box.get("1.0", "end-1c")
        prefix = "" if (not current or current.endswith((" ", "\n"))) else " "
        self.input_box.insert("insert", prefix + text + " ")
        self.input_view._segment_insert_line()
        self.input_box.focus_set()
        self._update_counts()
        self._set_status(self._t("mic_inserted"))

    # ================================================================ check
    def on_check(self):
        if self._checking:
            return
        text = self.input_box.get("1.0", "end-1c")
        if not text.strip():
            self._set_status(self._t("enter_text"))
            self.input_box.focus_set()
            return
        mode = self.config_obj.get("connection_mode", "direct")
        if mode == "direct" and not self.config_obj.has_api_key():
            self._set_status(self._t("need_key"))
            self.open_settings()
            return
        words = len(text.split())
        limit = self.proofreader.max_words
        if limit and words > limit:
            msg = self._t("over_limit", _fmt(words), _fmt(limit))
            self._set_status("⚠ " + msg)
            self.banner.show("warn", msg)
            return
        if self.banner.kind in ("warn",):
            self.banner.hide()
        self._checking = True
        self._check_started = time.time()
        self._check_words = words
        chunk = getattr(self.proofreader.engine, "chunk_words", 0) or 0
        self._check_parts = (-(-words // chunk)) if (mode == "lan_proxy" and chunk) else 1
        self.check_btn.configure(state="disabled", text=self._t("checking_btn2"))
        self.progress_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        self.progress.start()
        self._tick_progress()
        threading.Thread(target=self._run_check, args=(text,), daemon=True).start()

    def _tick_progress(self):
        if not self._checking:
            return
        secs = int(time.time() - self._check_started)
        if self._check_parts > 1:
            msg = self._t("checking_parts", _fmt(self._check_words), self._check_parts, secs)
        else:
            msg = self._t("checking_n", _fmt(self._check_words), secs)
        self.progress_label.configure(text=msg)
        self._set_status(msg)
        self.after(1000, self._tick_progress)

    def _run_check(self, text):
        t0 = time.time()
        try:
            result = self.proofreader.proofread(text)
        except Exception as exc:  # pragma: no cover - safety net
            self.after(0, lambda: self._check_done(None, 0, str(exc)))
            return
        self.after(0, lambda: self._check_done(result, time.time() - t0, None))

    def _check_done(self, result, elapsed, crash):
        self._checking = False
        self.progress.stop()
        self.progress_row.grid_forget()
        self.check_btn.configure(state="normal", text=self._t("check_btn2"))
        lang = self.config_obj.get("language", "en")
        if crash or not result.get("ok", True):
            msg = crash or (result.get("summary_si") if lang == "si" else result.get("summary_en")) \
                or result.get("message", "")
            msg = msg.lstrip("⚠️ ").strip()
            self._set_status("❌ " + msg)
            self.banner.show("danger" if result and result.get("error_kind") != "too_long" else "warn",
                             self._t("check_failed", msg))
            if result and result.get("error_kind") == "network":
                self._online = False
                self.conn_pill.set("bad", self._t("conn_offline"))
                self.beat_now()
            return
        self._result = result
        self._work_text = result["original"]
        self._issues = [dict(e) for e in result["errors"]]
        self._last_corrected_text = result.get("corrected_text", "")
        self.corrected_box.delete("1.0", "end")
        self.corrected_box.insert("1.0", self._last_corrected_text)
        self.corrected_view.segment_all()

        self._render_highlights(scroll_to_first=True)
        self._populate_issues()
        self._show_view("highlight")

        s = result["stats"]
        summary = self._t("result_summary", len(self._issues), _fmt(s["total_words"]), elapsed)
        self.stats_label.configure(text=summary)
        main = result.get("summary_si") if lang == "si" else result.get("summary_en")
        self._set_status(main or (self._t("no_errors") if not self._issues else summary))
        if result.get("parts_failed"):
            self.banner.show("warn", main or "")
        if self.config_obj.get("keep_history", True):
            self.history.add(result["original"], self._last_corrected_text,
                             s["total_words"], len(self._issues))

    # ======================================================= highlights
    def _render_highlights(self, scroll_to_first=False):
        rt = self.result_text
        yview = rt.yview()[0]
        rt.configure(state="normal")
        rt.delete("1.0", "end")
        rt.insert("1.0", self._work_text)
        segment_text(rt)
        first = None
        for e in self._issues:
            s, en = e.get("start"), e.get("end")
            if s is None or en is None:
                continue
            tag = "spell_error" if e.get("type") == "spelling" else "grammar_error"
            vs, ve = _visual_span(self._work_text, s, en)
            rt.tag_add(tag, "1.0+%dc" % vs, "1.0+%dc" % ve)
            if first is None:
                first = "1.0+%dc" % s
        if self._focused is not None and self._focused in self._issues:
            s, en = self._focused.get("start"), self._focused.get("end")
            if s is not None:
                vs, ve = _visual_span(self._work_text, s, en)
                rt.tag_add("focus", "1.0+%dc" % vs, "1.0+%dc" % ve)
        rt.configure(state="disabled")
        if scroll_to_first and first:
            rt.see(first)
        else:
            rt.yview_moveto(yview)

    def _populate_issues(self):
        for child in self.issues_frame.winfo_children():
            child.destroy()
        spell = sum(1 for e in self._issues if e.get("type") == "spelling")
        grammar = len(self._issues) - spell
        for pill, n, kind, key in ((self.spell_pill, spell, "bad", "spelling_n"),
                                   (self.grammar_pill, grammar, "warn", "grammar_n")):
            if n:
                pill.set(kind, self._t(key, n))
                pill.pack(side="left", padx=(10, 0))
            else:
                pill.pack_forget()
        acceptable = [e for e in self._issues if e.get("correction") and e.get("start") is not None]
        if acceptable:
            self.accept_all_btn.configure(text=self._t("accept_all", len(acceptable)))
            self.accept_all_btn.pack(side="right")
        else:
            self.accept_all_btn.pack_forget()

        if not self._issues:
            key = "issues_none" if self._result is not None and not self._result["errors"] \
                else ("issues_done" if self._result is not None else "issues_start")
            self._show_issues_placeholder(key)
            return
        lang = self.config_obj.get("language", "en")
        labels = {"accept": self._t("accept"), "ignore": self._t("ignore"),
                  "spelling": self._t("chip_spelling"), "grammar": self._t("chip_grammar"),
                  "encoding": self._t("chip_encoding"), "learned": self._t("chip_learned")}
        width = self.winfo_width()
        for e in self._issues:
            row = IssueRow(self.issues_frame, e, lang=lang, labels=labels,
                           on_accept=self.accept_issue, on_ignore=self.ignore_issue,
                           on_focus=self.focus_issue)
            row.set_wrap(width)
            row.pack(fill="x", padx=4, pady=3)

    def _show_issues_placeholder(self, key):
        for child in self.issues_frame.winfo_children():
            child.destroy()
        ok = key in ("issues_none", "issues_done")
        ctk.CTkLabel(self.issues_frame, text=("✓  " if ok else "") + self._t(key), anchor="w",
                     font=font(14, ok), text_color=TH.SUCCESS_TEXT if ok else TH.MUTED).pack(
            fill="x", padx=10, pady=14)

    # ===================================================== issue actions
    def _text_unchanged(self):
        """Accepting edits positions in the checked text; refuse if the user
        typed in the editor since the check."""
        if _norm(self.input_box.get("1.0", "end-1c")) != _norm(self._work_text):
            self._set_status("⚠ " + self._t("text_changed"))
            self.banner.show("warn", self._t("text_changed"))
            return False
        return True

    def _apply(self, issue):
        """Replace one issue's span in _work_text and shift later positions."""
        s, en = issue["start"], issue["end"]
        rep = issue.get("correction", "")
        self._work_text = self._work_text[:s] + rep + self._work_text[en:]
        delta = len(rep) - (en - s)
        remaining = []
        for e in self._issues:
            if e is issue:
                continue
            es, ee = e.get("start"), e.get("end")
            if es is not None and ee is not None:
                if es < en and ee > s:          # overlapped the replaced span
                    continue
                if es >= en:
                    e["start"], e["end"] = es + delta, ee + delta
            remaining.append(e)
        self._issues = remaining

    def _sync_editor(self):
        top = self.input_box.yview()[0]
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", self._work_text)
        self.input_view.segment_all()
        self.input_box.yview_moveto(top)
        self._update_counts()

    def accept_issue(self, issue):
        if issue not in self._issues or issue.get("start") is None or not self._text_unchanged():
            return
        self._apply(issue)
        self._focused = None
        self._sync_editor()
        self._render_highlights()
        self._populate_issues()
        self._set_status("✓ " + self._t("fixed_one", issue.get("original", ""),
                                        issue.get("correction", "")))

    def ignore_issue(self, issue):
        if issue in self._issues:
            self._issues.remove(issue)
            self._focused = None
            self._render_highlights()
            self._populate_issues()
            self._set_status(self._t("ignored_one", issue.get("original", "")))

    def accept_all(self):
        if not self._text_unchanged():
            return
        todo = sorted([e for e in self._issues if e.get("correction") and e.get("start") is not None],
                      key=lambda e: e["start"], reverse=True)   # back to front: no shifting
        for e in todo:
            if e in self._issues:
                self._apply(e)
        self._focused = None
        self._sync_editor()
        self._render_highlights()
        self._populate_issues()
        self._set_status("✓ " + self._t("accepted_all", len(todo)))

    def focus_issue(self, issue):
        self._focused = issue
        self._show_view("highlight")
        self._render_highlights()
        if issue.get("start") is not None:
            self.result_text.see("1.0+%dc" % issue["start"])

    def _on_highlight_click(self, event):
        index = self.result_text.index("@%d,%d" % (event.x, event.y))
        counted = self.result_text.count("1.0", index, "chars")
        offset = counted[0] if counted else 0
        for e in self._issues:
            s, en = e.get("start"), e.get("end")
            if s is None or en is None:
                continue
            vs, ve = _visual_span(self._work_text, s, en)
            if vs <= offset < ve:
                self.focus_issue(e)
                self._show_issue_popup(e)
                break

    def _show_issue_popup(self, issue):
        popup = ctk.CTkToplevel(self)
        popup.title("Issue")
        popup.geometry("460x300")
        popup.transient(self)
        popup.grab_set()
        popup.configure(fg_color=TH.WINDOW_BG)
        card = self._card(popup)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        is_spell = issue.get("type") == "spelling"
        ctk.CTkLabel(card, text="Spelling" if is_spell else "Grammar", font=font(13, True),
                     fg_color=TH.DANGER_SOFT if is_spell else TH.WARNING_SOFT,
                     text_color=TH.DANGER_TEXT if is_spell else TH.WARNING_TEXT,
                     corner_radius=8, height=26, width=90).pack(anchor="w", padx=16, pady=(16, 10))
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.pack(anchor="w", padx=16)
        ctk.CTkLabel(line, text=issue.get("original", ""), font=font(18),
                     text_color=TH.DANGER_TEXT).pack(side="left")
        if issue.get("correction"):
            ctk.CTkLabel(line, text="  →  ", font=font(16), text_color=TH.MUTED).pack(side="left")
            ctk.CTkLabel(line, text=issue["correction"], font=font(18, True),
                         text_color=TH.SUCCESS_TEXT).pack(side="left")
        for key, color in (("explanation_si", TH.TEXT), ("explanation_en", TH.MUTED)):
            if issue.get(key):
                ctk.CTkLabel(card, text=issue[key], anchor="w", justify="left", font=font(13),
                             wraplength=400, text_color=color).pack(anchor="w", padx=16, pady=(8, 0))
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=16, pady=14)
        if issue.get("correction") and issue.get("start") is not None:
            self._btn(btns, "accept", "success", reg=False, command=
                      lambda: (popup.destroy(), self.accept_issue(issue))).pack(
                side="left", expand=True, fill="x", padx=(0, 6))
        self._btn(btns, "ignore", "secondary", reg=False, command=
                  lambda: (popup.destroy(), self.ignore_issue(issue))).pack(
            side="left", expand=True, fill="x", padx=6)
        self._btn(btns, "close_btn", "ghost", reg=False, command= popup.destroy).pack(
            side="left", expand=True, fill="x", padx=(6, 0))

    # ================================================================ output
    def on_paste(self):
        text = clipboard_text(self)
        if text:
            self.input_view.insert_text("insert", text)
            self.input_box.see("insert")
            self._update_counts()
            self._set_status(self._t("pasted"))
            self.input_box.focus_set()

    def on_clear(self):
        self.input_box.delete("1.0", "end")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.corrected_box.delete("1.0", "end")
        self._result = None
        self._issues = []
        self._work_text = ""
        self._focused = None
        self._last_corrected_text = ""
        self._populate_issues()
        self._update_counts()
        self.stats_label.configure(text="")
        if self.banner.kind in ("warn",):
            self.banner.hide()
        self._set_status(self._t("ready"))
        self.input_box.focus_set()

    def on_copy(self):
        text = self.corrected_box.get("1.0", "end-1c")
        if not text.strip():
            self._set_status(self._t("nothing_copy"))
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("📋 " + self._t("copied"))

    def use_corrected(self):
        """Put the (possibly edited) corrected text into the editor."""
        text = self.corrected_box.get("1.0", "end-1c").strip()
        if not text:
            self._set_status(self._t("run_first"))
            return
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self.input_view.segment_all()
        self._work_text = text
        self._issues = []
        self._focused = None
        self._render_highlights()
        self._populate_issues()
        self._update_counts()
        self._set_status("✓ " + self._t("moved_to_editor"))

    def on_export(self):
        if not self._result:
            self._set_status(self._t("run_first"))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text file", "*.txt")],
            initialdir=os.path.join(os.path.expanduser("~"), "Desktop"),
            initialfile="sinhala_proofreader_report.txt", title="Export report")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._format_report(self._result))
            self._set_status("💾 Saved: %s" % os.path.basename(path))
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    def _format_report(self, result):
        s = result["stats"]
        mode = ("LAN Proxy (%s)" % self.config_obj.get("proxy_url")
                if result.get("mode") == "lan_proxy"
                else "Gemini AI (%s)" % self.config_obj.get("gemini_model"))
        lines = [
            "සිංහල ප්‍රතිශෝධන වාර්තාව / Sinhala Proofreader Report",
            "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Mode: %s" % mode, "",
            "Summary:",
            "Words: %d | Errors: %d (spelling: %d, grammar: %d)"
            % (s["total_words"], s["errors_found"], s["spell_errors"], s["grammar_errors"]),
            "", "Original:", result["original"],
            "", "Corrected:", self.corrected_box.get("1.0", "end-1c") or result.get("corrected_text", ""),
            "", "Error details:",
        ]
        if not result["errors"]:
            lines.append("(none)")
        for e in result["errors"]:
            tag = "SPELL" if e.get("type") == "spelling" else "GRAMMAR"
            lines.append("[%s] \"%s\" -> \"%s\"" % (tag, e.get("original", ""), e.get("correction", "")))
            if e.get("explanation_si"):
                lines.append("  සිංහල: %s" % e["explanation_si"])
            if e.get("explanation_en"):
                lines.append("  English: %s" % e["explanation_en"])
            lines.append("  Confidence: %d%%" % int(round(e.get("confidence", 0) * 100)))
        return "\n".join(lines)

    # ================================================================ history
    def open_history(self):
        win = ctk.CTkToplevel(self)
        win.title(self._t("history_btn"))
        win.geometry("720x560")
        win.transient(self)
        win.configure(fg_color=TH.WINDOW_BG)
        head = ctk.CTkFrame(win, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(head, text=self._t("history_title"), font=font(15, True),
                     text_color=TH.TEXT).pack(side="left")
        listing = ctk.CTkScrollableFrame(win, fg_color="transparent")

        def refresh():
            for c in listing.winfo_children():
                c.destroy()
            if not self.history.items:
                ctk.CTkLabel(listing, text=self._t("history_empty"), font=font(13),
                             text_color=TH.MUTED).pack(pady=30)
                return
            for i, item in enumerate(self.history.items):
                row = self._card(listing)
                row.pack(fill="x", padx=4, pady=4)
                row.grid_columnconfigure(0, weight=1)
                preview = " ".join(item["original"].split())
                preview = preview[:110] + ("…" if len(preview) > 110 else "")
                ctk.CTkLabel(row, text=preview, font=font(14), anchor="w", justify="left",
                             wraplength=470, text_color=TH.TEXT).grid(
                    row=0, column=0, sticky="w", padx=12, pady=(10, 0))
                ctk.CTkLabel(row, text=self._t("history_meta", item["time"], _fmt(item["words"]),
                                               item["issues"]),
                             font=font(12), text_color=TH.MUTED, anchor="w").grid(
                    row=1, column=0, sticky="w", padx=12, pady=(0, 10))
                btns = ctk.CTkFrame(row, fg_color="transparent")
                btns.grid(row=0, column=1, rowspan=2, padx=10)
                self._btn(btns, "history_open", "primary", reg=False, command=
                          lambda it=item: (self._restore(it), win.destroy()),
                          width=70, height=30, font=font(12, True)).pack(side="left", padx=2)
                self._btn(btns, "history_copy", "secondary", reg=False, command=
                          lambda it=item: self._copy_text(it["corrected"]),
                          width=64, height=30, font=font(12)).pack(side="left", padx=2)
                self._btn(btns, None, "ghost",
                          lambda idx=i: (self.history.remove(idx), refresh()),
                          text="✕", width=30, height=30).pack(side="left", padx=2)

        self._btn(head, "history_clear", "ghost", reg=False, command=
                  lambda: (self.history.clear(), refresh()), height=30,
                  font=font(12)).pack(side="right")
        listing.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        refresh()
        win.after(120, win.lift)

    def _restore(self, item):
        self.on_clear()
        self.input_box.insert("1.0", item["original"])
        self.corrected_box.insert("1.0", item.get("corrected", ""))
        self.input_view.segment_all()
        self.corrected_view.segment_all()
        self._last_corrected_text = item.get("corrected", "")
        self._work_text = item["original"]
        self._render_highlights()
        self._update_counts()
        self._show_view("corrected")
        self._set_status(self._t("history_opened"))

    def _copy_text(self, text):
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("📋 " + self._t("copied"))

    # ======================================================= self-learning
    def submit_manual_corrections(self):
        import difflib
        gemini_text = self._last_corrected_text
        human_text = self.corrected_box.get("1.0", "end-1c").strip()
        if not gemini_text or not human_text:
            self._set_status(self._t("run_first"))
            return
        if gemini_text == human_text:
            self._set_status(self._t("no_edits"))
            self._show_view("corrected")
            return
        gw, hw = gemini_text.split(), human_text.split()
        matcher = difflib.SequenceMatcher(None, gw, hw)
        corrections = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                wrong = " ".join(gw[i1:i2])
                correct = " ".join(hw[j1:j2])
                if wrong.strip() and correct.strip() and wrong != correct:
                    corrections.append({"wrong": wrong, "correct": correct,
                                        "type": "spelling" if len(wrong.split()) == 1 else "grammar"})
        if not corrections:
            self._set_status(self._t("no_edits"))
            return
        self._show_corrections_confirm_dialog(corrections)

    def _show_corrections_confirm_dialog(self, corrections):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Save Corrections?")
        dialog.geometry("560x440")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=TH.WINDOW_BG)
        card = self._card(dialog)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(card, text="Save these corrections to the learning database?",
                     font=font(15, True), text_color=TH.TEXT).pack(pady=12, padx=20)
        frame = ctk.CTkScrollableFrame(card, height=230, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=5)
        for c in corrections:
            row = self._card(frame)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text='"%s"  →  "%s"   [%s]' % (c["wrong"], c["correct"], c["type"]),
                         font=font(13), anchor="w", justify="left", wraplength=470,
                         text_color=TH.TEXT).pack(padx=12, pady=6, anchor="w")
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=12)

        def save_all():
            self._save_corrections_to_db(corrections)
            dialog.destroy()

        self._btn(btns, None, "success", save_all, text="✓ Save all", width=120).pack(side="left", padx=5)
        self._btn(btns, "set_cancel", "secondary", dialog.destroy, reg=False, width=100).pack(side="left", padx=5)
        dialog.after(120, dialog.lift)

    def _save_corrections_to_db(self, corrections):
        saved = 0
        for c in corrections:
            self.proofreader.corrections_db.record_correction(
                wrong=c["wrong"], correct=c["correct"], error_type=c["type"],
                added_by="gui_user", source="manual_edit")
            saved += 1
        if getattr(self.proofreader, "mode", "direct") == "lan_proxy":
            res = self.proofreader.engine.send_corrections(corrections)
            if res.get("status") == "error":
                self._set_status("⚠️ Local saved. Proxy sync failed: %s" % str(res.get("error"))[:50])
            else:
                self._set_status(self._t("saved_proxy", saved))
        else:
            self._set_status(self._t("saved_local", saved))

    # ================================================== dialogs / misc
    def open_settings(self):
        SettingsDialog(self, self.config_obj, on_saved=self._on_settings_saved)

    def _on_settings_saved(self):
        self._sync_theme_switch()
        self.proofreader.rebuild_engine()
        self._online = None
        self._update_dismissed = False
        self.retranslate()
        self._style_result_text()
        self._refresh_mode_ui()
        self.beat_now()
        self._set_status(self._t("settings_saved"))

    def _show_welcome(self):
        WelcomeDialog(self, on_add_key=self.open_settings, on_skip=self._refresh_mode_ui)

    def _sync_theme_switch(self):
        dark = self.config_obj.get("theme", "dark") == "dark"
        if dark:
            self.theme_switch.select()
        else:
            self.theme_switch.deselect()
        self._theme_label.configure(text=self._t("set_theme_dark" if dark else "set_theme_light"))

    def _toggle_theme(self):
        mode = "dark" if self.theme_switch.get() else "light"
        ctk.set_appearance_mode(mode)
        self.config_obj.set("theme", mode)
        self.config_obj.save()
        self._theme_label.configure(text=self._t("set_theme_dark" if mode == "dark" else "set_theme_light"))
        self._style_result_text()

    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _on_close(self):
        self._closing = True
        self._beat_now.set()
        try:
            zoomed = self.state() == "zoomed"
            self.config_obj.set("window_zoomed", zoomed)
            if not zoomed:
                self.config_obj.set("window_geometry", self.geometry())
            self.config_obj.save()
        except Exception:
            pass
        self.destroy()

    # ================================================================ i18n
    def _t(self, key, *args):
        return t(self.config_obj.get("language", "en"), key, *args)

    def _reg(self, widget, key):
        self._tr.append((widget, key))
        widget.configure(text=self._t(key))
        return widget

    def retranslate(self):
        for widget, key in self._tr:
            try:
                widget.configure(text=self._t(key))
            except Exception:
                pass
        self._set_tabs()
        self._show_view(getattr(self, "_view", "highlight"))
        self._sync_theme_switch()
        if not self._checking:
            self.check_btn.configure(text=self._t("check_btn2"))
        self.voice_btn.retranslate()
        self._populate_issues()
        self._update_counts()
