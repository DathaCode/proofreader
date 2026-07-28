# -*- coding: utf-8 -*-
"""
settings_dialog.py — connection mode, API key & preferences popup.

All labels are translated via gui/i18n and follow the chosen UI Language. Picking
a different UI Language re-labels the dialog live (preview before Save).
"""

import threading
import webbrowser

import customtkinter as ctk

from .widgets import font, StatusIndicator
from .i18n import t
from engine.gemini_engine import GeminiProofreader, GeminiError

AISTUDIO_URL = "https://aistudio.google.com/app/apikey"

# (model id, descriptor i18n key)
MODELS = [
    ("gemini-2.5-flash", "model_fast"),
    ("gemini-flash-latest", "model_latest"),
    ("gemini-2.5-pro", "model_pro"),
]


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, config, on_saved=None):
        super().__init__(master)
        self.config_obj = config
        self.on_saved = on_saved
        self._tr = []          # [(widget, text_func)] for live language preview
        self._show_key = False

        # Control variables (created first so _t() can read the language live).
        self.mode_var = ctk.StringVar(value=config.get("connection_mode", "direct"))
        self.model_var = ctk.StringVar(value=config.get("gemini_model", "gemini-2.5-flash"))
        self.theme_var = ctk.StringVar(value=config.get("theme", "dark"))
        self.lang_var = ctk.StringVar(value=config.get("language", "en"))

        self.geometry("560x740")
        self.minsize(520, 560)
        self.transient(master)
        self.grab_set()  # modal
        self._build()
        self._retranslate()
        self.after(120, self.lift)

    # ----- i18n helpers --------------------------------------------------
    def _lang(self):
        # Settings dialog is English-only chrome (the UI Language radio still
        # controls the MAIN window's language, which is saved on Save).
        return "en"

    def _t(self, key, *args):
        return t(self._lang(), key, *args)

    def _regk(self, widget, key):
        """Register a widget whose text is i18n key `key`."""
        self._tr.append((widget, lambda k=key: self._t(k)))
        return widget

    def _regf(self, widget, func):
        """Register a widget whose text is produced by func()."""
        self._tr.append((widget, func))
        return widget

    def _retranslate(self):
        self.title(self._t("set_title"))
        for widget, func in self._tr:
            try:
                widget.configure(text=func())
            except Exception:
                pass

    # ----- layout --------------------------------------------------------
    def _build(self):
        # Save / Cancel pinned to the bottom (outside the scroll area).
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=20, pady=14)
        self._regk(ctk.CTkButton(btns, command=self._save), "set_save").pack(
            side="left", expand=True, fill="x", padx=(0, 6))
        self._regk(ctk.CTkButton(btns, fg_color="gray40", hover_color="gray30",
                                 command=self.destroy), "set_cancel").pack(
            side="left", expand=True, fill="x", padx=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        pad = {"padx": 16, "pady": (10, 0)}

        self._regk(ctk.CTkLabel(body, font=font(20, True)), "set_title").pack(anchor="w", **pad)

        # ── CONNECTION MODE ──────────────────────────────────────────────
        self._regk(ctk.CTkLabel(body, font=font(15, True)), "set_conn_mode").pack(anchor="w", **pad)
        for value, key in [("direct", "set_mode_direct"), ("lan_proxy", "set_mode_lan")]:
            self._regk(ctk.CTkRadioButton(body, variable=self.mode_var, value=value,
                                          font=font(13), command=self._toggle_mode_fields),
                       key).pack(anchor="w", padx=30, pady=2)

        # Common frame anchors the position of the mode-specific frames.
        self.common_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.common_frame.pack(fill="x", side="bottom")

        # ── DIRECT-mode widgets ──────────────────────────────────────────
        self.direct_frame = ctk.CTkFrame(body, fg_color="transparent")

        self._regk(ctk.CTkLabel(self.direct_frame, font=font(15, True)), "set_api_key").pack(
            anchor="w", padx=4, pady=(10, 0))
        key_row = ctk.CTkFrame(self.direct_frame, fg_color="transparent")
        key_row.pack(fill="x", padx=4, pady=(2, 0))
        self.key_entry = ctk.CTkEntry(key_row, placeholder_text="AIza... / AQ...",
                                      show="•", font=font(14))
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.key_entry.insert(0, self.config_obj.get_api_key())
        ctk.CTkButton(key_row, text="👁️", width=40, command=self._toggle_show).pack(
            side="left", padx=(6, 0))

        test_row = ctk.CTkFrame(self.direct_frame, fg_color="transparent")
        test_row.pack(fill="x", padx=4, pady=(8, 0))
        self.test_btn = self._regk(ctk.CTkButton(test_row, command=self._test_connection),
                                   "set_test_conn")
        self.test_btn.pack(side="left")
        self.test_status = StatusIndicator(self.direct_frame, font=font(13))
        self.test_status.pack(anchor="w", padx=4, pady=(6, 0))

        help_box = ctk.CTkFrame(self.direct_frame)
        help_box.pack(fill="x", padx=4, pady=(12, 0))
        self._regk(ctk.CTkLabel(help_box, font=font(13, True), anchor="w", justify="left"),
                   "set_help_title").pack(anchor="w", padx=10, pady=(8, 2))
        self._regk(ctk.CTkLabel(help_box, font=font(13), anchor="w", justify="left"),
                   "set_help_steps").pack(anchor="w", padx=10, pady=(0, 6))
        self._regk(ctk.CTkButton(help_box, fg_color="gray30", hover_color="gray25",
                                 command=lambda: webbrowser.open(AISTUDIO_URL)),
                   "set_open_aistudio").pack(anchor="w", padx=10, pady=(0, 10))

        self._regk(ctk.CTkLabel(self.direct_frame, font=font(14, True)), "set_model").pack(
            anchor="w", padx=4, pady=(10, 0))
        for value, desc_key in MODELS:
            rb = ctk.CTkRadioButton(self.direct_frame, variable=self.model_var,
                                    value=value, font=font(13))
            self._regf(rb, lambda v=value, k=desc_key: "%s  (%s)" % (v, self._t(k)))
            rb.pack(anchor="w", padx=24, pady=2)

        # ── LAN-PROXY widgets ────────────────────────────────────────────
        self.proxy_frame = ctk.CTkFrame(body, fg_color="transparent")
        self._regk(ctk.CTkLabel(self.proxy_frame, font=font(14, True)), "set_proxy_url").pack(
            anchor="w", padx=4, pady=(10, 0))
        self.proxy_url_entry = ctk.CTkEntry(self.proxy_frame,
                                            placeholder_text="http://192.168.1.100:8765",
                                            font=font(13))
        self.proxy_url_entry.pack(fill="x", padx=4, pady=3)
        self.proxy_url_entry.insert(0, self.config_obj.get("proxy_url", "http://192.168.1.100:8765"))
        self._regk(ctk.CTkButton(self.proxy_frame, command=self._test_proxy),
                   "set_test_proxy").pack(anchor="w", padx=4, pady=5)
        self.proxy_status_label = StatusIndicator(self.proxy_frame, font=font(13))
        self.proxy_status_label.pack(anchor="w", padx=4)
        self._regk(ctk.CTkLabel(self.proxy_frame, font=font(12), text_color="gray",
                                anchor="w", justify="left", wraplength=480),
                   "set_proxy_hint").pack(anchor="w", padx=4, pady=(6, 0))

        # ── COMMON: theme + language ─────────────────────────────────────
        row = ctk.CTkFrame(self.common_frame, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(14, 0))
        theme_col = ctk.CTkFrame(row, fg_color="transparent")
        theme_col.pack(side="left", expand=True, anchor="w")
        self._regk(ctk.CTkLabel(theme_col, font=font(14, True)), "set_theme").pack(anchor="w")
        for value, key in [("dark", "set_theme_dark"), ("light", "set_theme_light")]:
            self._regk(ctk.CTkRadioButton(theme_col, variable=self.theme_var, value=value,
                                          font=font(13)), key).pack(anchor="w", pady=1)
        lang_col = ctk.CTkFrame(row, fg_color="transparent")
        lang_col.pack(side="left", expand=True, anchor="w")
        self._regk(ctk.CTkLabel(lang_col, font=font(14, True)), "set_lang").pack(anchor="w")
        for value, label in [("si", "සිංහල"), ("en", "English")]:
            # Language names stay as-is; selecting one re-labels the dialog live.
            ctk.CTkRadioButton(lang_col, text=label, variable=self.lang_var, value=value,
                               font=font(13), command=self._retranslate).pack(anchor="w", pady=1)

        self._toggle_mode_fields()

    # ----- behaviour -----------------------------------------------------
    def _toggle_mode_fields(self):
        self.direct_frame.pack_forget()
        self.proxy_frame.pack_forget()
        if self.mode_var.get() == "lan_proxy":
            self.proxy_frame.pack(fill="x", padx=16, before=self.common_frame)
        else:
            self.direct_frame.pack(fill="x", padx=16, before=self.common_frame)

    def _toggle_show(self):
        self._show_key = not self._show_key
        self.key_entry.configure(show="" if self._show_key else "•")

    def _test_connection(self):
        key = self.key_entry.get().strip()
        if not self.config_obj.validate_api_key_format(key):
            self.test_status.set_status(False, self._t("set_key_empty"))
            return
        self.test_btn.configure(state="disabled", text=self._t("set_testing"))
        self.test_status.configure(text="⏳ ...", text_color="gray")

        def run():
            try:
                ok, msg = GeminiProofreader(key, self.model_var.get()).test_connection()
            except GeminiError as exc:
                ok, msg = False, exc.message_si
            except Exception as exc:  # pragma: no cover
                ok, msg = False, str(exc)
            self.after(0, lambda: self._test_done(ok, msg))

        threading.Thread(target=run, daemon=True).start()

    def _test_done(self, ok, msg):
        self.test_btn.configure(state="normal", text=self._t("set_test_conn"))
        self.test_status.set_status(ok, msg)

    def _test_proxy(self):
        url = self.proxy_url_entry.get().strip()
        if not url:
            self.proxy_status_label.set_status(False, self._t("set_proxy_empty"))
            return
        self.proxy_status_label.configure(text="⏳ ...", text_color="gray")

        def run():
            try:
                from engine.lan_proxy_engine import LanProxyProofreader
                ok, msg = LanProxyProofreader(url).test_connection()
            except Exception as exc:  # pragma: no cover
                ok, msg = False, str(exc)[:100]
            self.after(0, lambda: self.proxy_status_label.set_status(ok, msg))

        threading.Thread(target=run, daemon=True).start()

    def _save(self):
        key = self.key_entry.get().strip()
        if key and not self.config_obj.validate_api_key_format(key):
            self.test_status.set_status(False, self._t("set_key_empty"))
            return
        self.config_obj.set("connection_mode", self.mode_var.get())
        self.config_obj.set("proxy_url", self.proxy_url_entry.get().strip())
        self.config_obj.set("gemini_api_key", key)
        self.config_obj.set("gemini_model", self.model_var.get())
        self.config_obj.set("theme", self.theme_var.get())
        self.config_obj.set("language", self.lang_var.get())
        self.config_obj.save()
        ctk.set_appearance_mode(self.theme_var.get())
        if self.on_saved:
            self.on_saved()
        self.destroy()
