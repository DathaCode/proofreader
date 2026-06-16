# -*- coding: utf-8 -*-
"""
main_window.py — the Sinhala Proofreader main application window.

Layout: a modern two-pane workspace — Input (left 50%) and highlighted Results
(right 50%) — with the errors list below. The corrected text opens in its own
window. Styled for both dark and light themes via gui/theme.py.
"""

import os
import sys
import time
import threading
import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from engine.proofreader import SinhalaProofreader
from .widgets import font, sinhala_family, StatusIndicator, ErrorRow
from .settings_dialog import SettingsDialog
from .welcome_dialog import WelcomeDialog
from .i18n import t
from . import theme as TH

try:
    from version import __version__ as _APP_VER
except Exception:
    _APP_VER = "4.1"

APP_TITLE_EN = "Sinhala Proofreader"
VERSION = "v" + _APP_VER


def _resource_path(*parts):
    """Resolve a bundled resource both in dev and inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class MainWindow(ctk.CTk):
    def __init__(self, config):
        super().__init__()
        self.config_obj = config
        self.proofreader = SinhalaProofreader(config)
        self._last_result = None
        self._last_corrected_text = ""
        self._tr = []                 # [(widget, key)] for live language switching
        self.corrected_window = None  # separate Toplevel
        self.corrected_box = None

        ctk.set_appearance_mode(config.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self.title("%s  —  %s" % (APP_TITLE_EN, VERSION))
        self.geometry("1300x840")
        self.minsize(1080, 720)
        self.configure(fg_color=TH.WINDOW_BG)
        self._set_app_icon()

        self._build_header()
        self._build_mode_bar()
        self._build_body()
        self._build_error_list()
        self._build_statusbar()

        self.bind("<Control-Return>", lambda _e: self.on_check())
        self.bind("<Control-l>", lambda _e: self.on_clear())
        self.bind("<Control-L>", lambda _e: self.on_clear())

        self._refresh_mode_ui()

        if self.config_obj.get("connection_mode", "direct") == "lan_proxy":
            threading.Thread(
                target=self.proofreader.sync_corrections_from_proxy, daemon=True
            ).start()

        if (self.config_obj.get("connection_mode", "direct") == "direct"
                and not self.config_obj.has_api_key()):
            self.after(300, self._show_welcome)

    def _set_app_icon(self):
        """Set the window / taskbar icon from assets/. Uses the multi-size .ico
        on Windows (crisp title bar + taskbar) and the .png elsewhere; the PNG is
        also set as the inherited default so child Toplevels share the icon."""
        ico = _resource_path("assets", "icon.ico")
        png = _resource_path("assets", "icon.png")
        try:
            if os.path.exists(png):
                self._icon_image = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_image)  # default for all windows
        except Exception:
            pass
        try:
            if os.name == "nt" and os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ================================================================ build
    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=TH.CARD_BG, corner_radius=TH.R_CARD,
                            border_width=1, border_color=TH.BORDER)

    def _primary(self, parent, key=None, command=None, **kw):
        b = ctk.CTkButton(parent, fg_color=TH.ACCENT, hover_color=TH.ACCENT_HOVER,
                          corner_radius=TH.R_BTN, font=font(13, True), command=command, **kw)
        return self._reg(b, key) if key else b

    def _secondary(self, parent, key=None, command=None, **kw):
        b = ctk.CTkButton(parent, fg_color=TH.NEUTRAL, hover_color=TH.NEUTRAL_HOVER,
                          text_color=TH.TEXT, corner_radius=TH.R_BTN, font=font(13),
                          command=command, **kw)
        return self._reg(b, key) if key else b

    def _build_header(self):
        header = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color=TH.HEADER_BG)
        header.pack(fill="x")
        accent = ctk.CTkFrame(self, height=3, corner_radius=0, fg_color=TH.ACCENT)
        accent.pack(fill="x")

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", padx=20, pady=10)
        self._reg(ctk.CTkLabel(title, font=font(22, True), text_color=TH.TEXT),
                  "app_title").pack(anchor="w")
        self._reg(ctk.CTkLabel(title, font=font(12), text_color=TH.MUTED),
                  "app_subtitle").pack(anchor="w")

        self._primary(header, key="settings_btn", command=self.open_settings,
                      width=120, height=36).pack(side="right", padx=(6, 20), pady=10)
        self.theme_switch = ctk.CTkSwitch(header, text="🌙 Dark", command=self._toggle_theme,
                                          progress_color=TH.ACCENT)
        if self.config_obj.get("theme", "dark") == "dark":
            self.theme_switch.select()
        else:
            self.theme_switch.configure(text="☀️ Light")
        self.theme_switch.pack(side="right", padx=10)

    def _build_mode_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=0, fg_color=TH.BAR_BG, height=44)
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text="⚡ Gemini AI", font=font(14, True),
                     text_color=TH.ACCENT).pack(side="left", padx=(20, 8), pady=8)
        self.model_label = ctk.CTkLabel(bar, text="", font=font(12), text_color=TH.MUTED)
        self.model_label.pack(side="left", padx=4)
        self.conn_status = StatusIndicator(bar, font=font(13))
        self.conn_status.pack(side="right", padx=18)

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(12, 6))
        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")
        body.grid_rowconfigure(0, weight=1)
        self._build_input_panel(body)
        self._build_results_panel(body)

    def _build_input_panel(self, parent):
        left = self._card(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._reg(ctk.CTkLabel(left, anchor="w", font=font(15, True), text_color=TH.TEXT),
                  "input_label").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        self.input_box = ctk.CTkTextbox(left, font=font(16), wrap="word",
                                        corner_radius=TH.R_BOX, border_width=1,
                                        border_color=TH.BORDER)
        self.input_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        self.input_box.bind("<KeyRelease>", self._update_counts)

        self.count_label = ctk.CTkLabel(left, text="Words: 0 | Chars: 0", anchor="w",
                                        font=font(12), text_color=TH.MUTED)
        self.count_label.grid(row=2, column=0, sticky="ew", padx=16)

        self._reg(ctk.CTkLabel(left, anchor="w", font=font(12), text_color=TH.MUTED),
                  "input_hint").grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 0))

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 14))
        self.check_btn = self._primary(btns, key="check_btn", command=self.on_check, height=38)
        self.check_btn.pack(side="left", padx=(0, 8))
        self._secondary(btns, key="clear_btn", command=self.on_clear, height=38).pack(side="left")

    def _build_results_panel(self, parent):
        right = self._card(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._reg(ctk.CTkLabel(right, anchor="w", font=font(15, True), text_color=TH.TEXT),
                  "results_label").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        text_wrap = ctk.CTkFrame(right, fg_color="transparent")
        text_wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        text_wrap.grid_rowconfigure(0, weight=1)
        text_wrap.grid_columnconfigure(0, weight=1)
        self.result_text = tk.Text(text_wrap, font=(sinhala_family(), 16), wrap="word",
                                   relief="flat", padx=10, pady=10, borderwidth=0,
                                   highlightthickness=0)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        scroll = ctk.CTkScrollbar(text_wrap, command=self.result_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=scroll.set)
        self._style_result_text()
        self.result_text.configure(state="disabled")

        self._reg(ctk.CTkLabel(right, anchor="w", font=font(12), text_color=TH.MUTED),
                  "results_hint").grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 2))

        foot = ctk.CTkFrame(right, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 14))
        self._primary(foot, key="open_corrected", command=self.open_corrected_window,
                      height=38).pack(side="left")
        save = ctk.CTkButton(foot, command=self.apply_all_fixes, fg_color=TH.SUCCESS,
                             hover_color=TH.SUCCESS_HOVER, corner_radius=TH.R_BTN,
                             font=font(13, True), height=38)
        self._reg(save, "apply_all")
        save.pack(side="left", padx=(8, 0))

    def _build_error_list(self):
        wrap = self._card(self)
        wrap.pack(fill="x", padx=16, pady=6)
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 0))
        self._reg(ctk.CTkLabel(head, anchor="w", font=font(15, True), text_color=TH.TEXT),
                  "errors_label").pack(side="left", padx=8, pady=4)
        self.total_label = ctk.CTkLabel(head, text="Total: 0 errors", anchor="e",
                                        font=font(13), text_color=TH.MUTED)
        self.total_label.pack(side="right", padx=8)
        self.errors_frame = ctk.CTkScrollableFrame(wrap, height=140, label_text="",
                                                   fg_color="transparent")
        self.errors_frame.pack(fill="x", padx=8, pady=(0, 10))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color=TH.BAR_BG)
        bar.pack(fill="x", side="bottom")
        self.status_label = ctk.CTkLabel(bar, text=self._t("ready"), anchor="w",
                                         font=font(12), text_color=TH.MUTED)
        self.status_label.pack(side="left", padx=16)
        self.stats_label = ctk.CTkLabel(bar, text="", anchor="e", font=font(12),
                                        text_color=TH.MUTED)
        self.stats_label.pack(side="right", padx=16)

    # ===================================================== corrected window
    def _ensure_corrected_window(self):
        if self.corrected_window is not None and self.corrected_window.winfo_exists():
            return
        win = ctk.CTkToplevel(self)
        win.title(self._t("corrected_title"))
        win.geometry("760x600")
        win.minsize(520, 380)
        win.configure(fg_color=TH.WINDOW_BG)
        # Hide instead of destroy so the widgets persist.
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self.corrected_window = win

        card = self._card(win)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self._reg(ctk.CTkLabel(card, anchor="w", font=font(16, True), text_color=TH.TEXT),
                  "corrected_label").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        self._reg(ctk.CTkLabel(card, anchor="w", font=font(12), text_color=TH.MUTED,
                               justify="left"), "corrected_hint").grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        self.corrected_box = ctk.CTkTextbox(card, font=font(16), wrap="word",
                                            corner_radius=TH.R_BOX, border_width=1,
                                            border_color=TH.BORDER)
        self.corrected_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=6)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 14))
        self._primary(btns, key="copy_btn", command=self.on_copy, height=38).pack(side="left", padx=(0, 8))
        self._secondary(btns, key="export_btn", command=self.on_export, height=38).pack(side="left", padx=(0, 8))
        save = ctk.CTkButton(btns, command=self.submit_manual_corrections,
                             fg_color=TH.SUCCESS, hover_color=TH.SUCCESS_HOVER,
                             corner_radius=TH.R_BTN, font=font(13, True), height=38)
        self._reg(save, "save_corr_btn")
        save.pack(side="left", padx=(0, 8))
        self._secondary(btns, key="close_btn", command=win.withdraw, height=38, width=90).pack(side="right")

    def _show_corrected(self, text):
        self._ensure_corrected_window()
        self.corrected_box.delete("1.0", "end")
        self.corrected_box.insert("1.0", text)
        win = self.corrected_window
        win.deiconify()
        win.lift()
        # Park it to the right of the main window the first time.
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + self.winfo_width() - 40
            y = self.winfo_rooty() + 80
            win.geometry("+%d+%d" % (max(0, x - 740), y))
        except Exception:
            pass

    def open_corrected_window(self):
        self._ensure_corrected_window()
        if not self.corrected_box.get("1.0", "end-1c").strip():
            self.corrected_box.insert("1.0", self._last_corrected_text)
        self.corrected_window.deiconify()
        self.corrected_window.lift()

    def apply_all_fixes(self):
        """One-click accept: replace the input text with the corrected version."""
        # Prefer any edits the user made in the corrected window.
        text = ""
        if self.corrected_box is not None:
            text = self.corrected_box.get("1.0", "end-1c").strip()
        if not text:
            text = self._last_corrected_text
        if not text:
            self._set_status(self._t("run_first"))
            return
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self._update_counts()
        self._set_status(self._t("applied_all"))

    # ============================================================ behaviour
    def _style_result_text(self):
        c = TH.result_colors()
        self.result_text.configure(bg=c["bg"], fg=c["fg"], insertbackground=c["insert"])
        self.result_text.tag_configure("spell_error", background=TH.SPELL_BG,
                                       foreground="white", font=(sinhala_family(), 16, "bold"))
        self.result_text.tag_configure("grammar_error", background=TH.GRAMMAR_BG,
                                       foreground="white", font=(sinhala_family(), 16))
        self.result_text.tag_configure("sel", background=c["sel"])

    def _update_counts(self, _e=None):
        text = self.input_box.get("1.0", "end-1c")
        self.count_label.configure(text="Words: %d | Chars: %d" % (len(text.split()), len(text)))

    def _refresh_mode_ui(self):
        mode = self.config_obj.get("connection_mode", "direct")
        if mode == "lan_proxy":
            self.model_label.configure(text="🌐 LAN Proxy → %s" % self.config_obj.get("proxy_url", ""))
            self.conn_status.set_status(True, self._t("lan_mode"))
        else:
            self.model_label.configure(text="(%s)" % self.config_obj.get("gemini_model", "gemini-2.5-flash"))
            if self.config_obj.has_api_key():
                self.conn_status.set_status(True, self._t("key_ready"))
            else:
                self.conn_status.set_status(False, self._t("key_missing"))

    # ----- check ---------------------------------------------------------
    def on_check(self):
        text = self.input_box.get("1.0", "end-1c")
        if not text.strip():
            self._set_status(self._t("enter_text"))
            return
        mode = self.config_obj.get("connection_mode", "direct")
        if mode == "direct" and not self.config_obj.has_api_key():
            self._set_status(self._t("need_key"))
            self.open_settings()
            return
        self.check_btn.configure(state="disabled", text=self._t("checking_btn"))
        self._set_status(self._t("checking_lan") if mode == "lan_proxy" else self._t("checking_direct"))
        threading.Thread(target=self._run_check, args=(text,), daemon=True).start()

    def _run_check(self, text):
        t0 = time.time()
        try:
            result = self.proofreader.proofread(
                text, on_progress=lambda m: self.after(0, lambda: self._set_status("⏱️ " + m))
            )
        except Exception as exc:  # pragma: no cover - safety net
            self.after(0, lambda: self._check_failed(str(exc)))
            return
        elapsed = time.time() - t0
        self.after(0, lambda: self._render(result, elapsed))

    def _check_failed(self, msg):
        self.check_btn.configure(state="normal", text=self._t("check_btn"))
        self._set_status("❌ " + msg)

    def _render(self, result, elapsed):
        self._last_result = result
        self.check_btn.configure(state="normal", text=self._t("check_btn"))

        if not result.get("ok", True):
            lang = self.config_obj.get("language", "en")
            msg = result.get("summary_si") if lang == "si" else result.get("summary_en")
            self._set_status("❌ " + (msg or result.get("message", "")))
            messagebox.showerror(
                "Gemini Error",
                (result.get("summary_si", "") + "\n\n" + result.get("summary_en", "")).strip(),
            )
            return

        # Highlighted original.
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", result["original"])
        first_index = None
        for e in result["errors"]:
            start, end = e.get("start"), e.get("end")
            if start is None or end is None:
                continue
            tag = "spell_error" if e.get("type") == "spelling" else "grammar_error"
            self.result_text.tag_add(tag, "1.0+%dc" % start, "1.0+%dc" % end)
            if first_index is None:
                first_index = "1.0+%dc" % start
        self.result_text.tag_bind("spell_error", "<Button-1>", self._on_highlight_click)
        self.result_text.tag_bind("grammar_error", "<Button-1>", self._on_highlight_click)
        if first_index:
            self.result_text.see(first_index)
        self.result_text.configure(state="disabled")

        # Corrected text -> its own window.
        self._last_corrected_text = result.get("corrected_text", "")
        self._show_corrected(self._last_corrected_text)

        self._populate_errors(result["errors"])

        s = result["stats"]
        self.total_label.configure(text=self._t("total_errors", s["errors_found"]))
        mode_txt = "LAN Proxy" if result.get("mode") == "lan_proxy" else "Gemini AI"
        pre = result.get("pre_fixed_count", 0)
        pre_txt = " | ⚡%d auto" % pre if pre else ""
        self.stats_label.configure(
            text="📊 Words: %d | Errors: %d (S:%d, G:%d, E:%d)%s | %s | %.1fs"
            % (s["total_words"], s["errors_found"], s["spell_errors"],
               s["grammar_errors"], s.get("encoding_errors", 0), pre_txt, mode_txt, elapsed)
        )

        lang = self.config_obj.get("language", "en")
        summary = result.get("summary_si") if lang == "si" else result.get("summary_en")
        self._set_status(summary or self._t("no_errors"))
        self._update_db_status()

    def _update_db_status(self):
        try:
            st = self.proofreader.corrections_db.get_stats()
            self.conn_status.set_status(True, "DB: %d | ⚡ %d precheck" % (st["total"], st["precheck"]))
        except Exception:
            pass

    def _populate_errors(self, errors):
        for child in self.errors_frame.winfo_children():
            child.destroy()
        if not errors:
            ctk.CTkLabel(self.errors_frame, text=self._t("no_errors_row"), anchor="w",
                         font=font(14), text_color=TH.MUTED).pack(fill="x", padx=6, pady=6)
            return
        for e in errors:
            ErrorRow(self.errors_frame, e, on_click=self._jump_to_error).pack(
                fill="x", padx=2, pady=1)

    # ----- error interaction --------------------------------------------
    def _jump_to_error(self, error):
        start, end = error.get("start"), error.get("end")
        if start is None or end is None:
            self._set_status(error.get("explanation_si", "") or error.get("explanation_en", ""))
            return
        self.result_text.configure(state="normal")
        self.result_text.tag_remove("sel", "1.0", "end")
        self.result_text.tag_add("sel", "1.0+%dc" % start, "1.0+%dc" % end)
        self.result_text.see("1.0+%dc" % start)
        self.result_text.configure(state="disabled")
        self._show_error_popup(error)

    def _on_highlight_click(self, event):
        index = self.result_text.index("@%d,%d" % (event.x, event.y))
        counted = self.result_text.count("1.0", index, "chars")
        offset = counted[0] if counted else 0
        if not self._last_result:
            return
        for e in self._last_result["errors"]:
            s, en = e.get("start"), e.get("end")
            if s is not None and en is not None and s <= offset < en:
                self._show_error_popup(e)
                break

    def _show_error_popup(self, error):
        popup = ctk.CTkToplevel(self)
        popup.title("Error details")
        popup.geometry("440x320")
        popup.transient(self)
        popup.grab_set()
        popup.configure(fg_color=TH.WINDOW_BG)
        card = self._card(popup)
        card.pack(fill="both", expand=True, padx=12, pady=12)

        is_spell = error.get("type") == "spelling"
        ctk.CTkLabel(card, text="%s %s" % ("❌" if is_spell else "⚠️",
                     "Spelling" if is_spell else "Grammar"),
                     font=font(18, True), text_color=TH.TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(card, text="Wrong:  %s" % error.get("original", ""), anchor="w",
                     font=font(15), text_color=TH.TEXT).pack(anchor="w", padx=16, pady=2)
        correction = error.get("correction", "")
        if correction:
            ctk.CTkLabel(card, text="Correct:  %s" % correction, anchor="w",
                         font=font(15, True), text_color=TH.SUCCESS).pack(anchor="w", padx=16, pady=2)
        if error.get("explanation_si"):
            ctk.CTkLabel(card, text="සිංහල:  %s" % error["explanation_si"], anchor="w",
                         justify="left", font=font(13), wraplength=390, text_color=TH.TEXT).pack(anchor="w", padx=16, pady=(8, 2))
        if error.get("explanation_en"):
            ctk.CTkLabel(card, text="English:  %s" % error["explanation_en"], anchor="w",
                         justify="left", font=font(13), wraplength=390, text_color=TH.MUTED).pack(anchor="w", padx=16, pady=2)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=16, pady=14)
        if correction and error.get("start") is not None:
            ctk.CTkButton(btns, text="✔ Apply Fix", fg_color=TH.ACCENT, hover_color=TH.ACCENT_HOVER,
                          corner_radius=TH.R_BTN,
                          command=lambda: (self._apply_fix(error), popup.destroy())).pack(
                side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(btns, text=self._t("close_btn"), fg_color=TH.NEUTRAL, text_color=TH.TEXT,
                      hover_color=TH.NEUTRAL_HOVER, corner_radius=TH.R_BTN,
                      command=popup.destroy).pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _apply_fix(self, error):
        start, end = error.get("start"), error.get("end")
        if start is None or end is None:
            return
        self.input_box.delete("1.0+%dc" % start, "1.0+%dc" % end)
        self.input_box.insert("1.0+%dc" % start, error.get("correction", ""))
        self._update_counts()
        self.on_check()

    # ----- output --------------------------------------------------------
    def on_clear(self):
        self.input_box.delete("1.0", "end")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        if self.corrected_box is not None:
            self.corrected_box.delete("1.0", "end")
        for child in self.errors_frame.winfo_children():
            child.destroy()
        self._last_result = None
        self._last_corrected_text = ""
        self._update_counts()
        self.total_label.configure(text=self._t("total_errors", 0))
        self.stats_label.configure(text="")
        self._set_status(self._t("ready"))

    def on_copy(self):
        if self.corrected_box is None:
            self._set_status(self._t("nothing_copy"))
            return
        text = self.corrected_box.get("1.0", "end-1c")
        if not text.strip():
            self._set_status(self._t("nothing_copy"))
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status(self._t("copied"))

    def on_export(self):
        if not self._last_result:
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
                f.write(self._format_report(self._last_result))
            self._set_status("💾 Saved: %s" % os.path.basename(path))
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    def _format_report(self, result):
        s = result["stats"]
        mode = "Gemini AI (%s)" % self.config_obj.get("gemini_model")
        lines = [
            "සිංහල ප්‍රතිශෝධන වාර්තාව / Sinhala Proofreader Report",
            "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Mode: %s" % mode, "",
            "📊 Summary:",
            "Words: %d | Errors: %d (spelling: %d, grammar: %d)"
            % (s["total_words"], s["errors_found"], s["spell_errors"], s["grammar_errors"]),
            "", "📝 Original:", result["original"],
            "", "✅ Corrected:", result.get("corrected_text", ""),
            "", "❌ Error Details:",
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

    # ----- self-learning corrections ------------------------------------
    def submit_manual_corrections(self):
        import difflib
        gemini_text = getattr(self, "_last_corrected_text", "")
        human_text = self.corrected_box.get("1.0", "end-1c").strip() if self.corrected_box else ""
        if not gemini_text or not human_text:
            self._set_status(self._t("run_first"))
            return
        if gemini_text == human_text:
            self._set_status(self._t("no_edits"))
            return

        gw, hw = gemini_text.split(), human_text.split()
        matcher = difflib.SequenceMatcher(None, gw, hw)
        corrections = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                wrong = " ".join(gw[i1:i2]); correct = " ".join(hw[j1:j2])
                if wrong.strip() and correct.strip() and wrong != correct:
                    corrections.append({"wrong": wrong, "correct": correct,
                                        "type": "spelling" if len(wrong.split()) == 1 else "grammar"})
        if not corrections:
            self._set_status(self._t("no_edits"))
            return
        self._show_corrections_confirm_dialog(corrections)

    def _show_corrections_confirm_dialog(self, corrections):
        parent = self.corrected_window or self
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Save Corrections?")
        dialog.geometry("560x440")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(fg_color=TH.WINDOW_BG)
        card = self._card(dialog)
        card.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(card, text="✍️ Save these corrections to the learning database?",
                     font=font(15, True), text_color=TH.TEXT).pack(pady=12, padx=20)
        frame = ctk.CTkScrollableFrame(card, height=230, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=5)
        for c in corrections:
            row = self._card(frame)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text='❌ "%s"  →  ✅ "%s"   [%s]' % (c["wrong"], c["correct"], c["type"]),
                         font=font(13), anchor="w", justify="left", wraplength=470,
                         text_color=TH.TEXT).pack(padx=12, pady=6, anchor="w")

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=12)

        def save_all():
            self._save_corrections_to_db(corrections)
            dialog.destroy()

        ctk.CTkButton(btns, text="✅ Save All", command=save_all, corner_radius=TH.R_BTN,
                      fg_color=TH.SUCCESS, hover_color=TH.SUCCESS_HOVER).pack(side="left", padx=5)
        ctk.CTkButton(btns, text="❌ Cancel", command=dialog.destroy, corner_radius=TH.R_BTN,
                      fg_color=TH.DANGER, hover_color=TH.DANGER_HOVER).pack(side="left", padx=5)
        dialog.after(120, dialog.lift)

    def _save_corrections_to_db(self, corrections):
        saved = 0
        for c in corrections:
            self.proofreader.corrections_db.record_correction(
                wrong=c["wrong"], correct=c["correct"], error_type=c["type"],
                added_by="gui_user", source="manual_edit")
            saved += 1
        if getattr(self.proofreader, "mode", "direct") == "lan_proxy":
            try:
                self.proofreader.engine.send_corrections(corrections)
                self._set_status(self._t("saved_proxy", saved))
            except Exception as e:
                self._set_status("⚠️ Local saved. Proxy sync failed: %s" % str(e)[:50])
        else:
            self._set_status(self._t("saved_local", saved))
        self._update_db_status()

    # ----- dialogs / misc ------------------------------------------------
    def open_settings(self):
        SettingsDialog(self, self.config_obj, on_saved=self._on_settings_saved)

    def _on_settings_saved(self):
        if self.config_obj.get("theme", "dark") == "dark":
            self.theme_switch.select(); self.theme_switch.configure(text="🌙 Dark")
        else:
            self.theme_switch.deselect(); self.theme_switch.configure(text="☀️ Light")
        self.proofreader.rebuild_engine()
        self.retranslate()
        self._style_result_text()
        self._refresh_mode_ui()
        self._set_status(self._t("settings_saved"))

    def _show_welcome(self):
        WelcomeDialog(self, on_add_key=self.open_settings, on_skip=self._welcome_skip)

    def _welcome_skip(self):
        self._refresh_mode_ui()

    def _toggle_theme(self):
        mode = "dark" if self.theme_switch.get() else "light"
        ctk.set_appearance_mode(mode)
        self.config_obj.set("theme", mode)
        self.config_obj.save()
        self.theme_switch.configure(text="🌙 Dark" if mode == "dark" else "☀️ Light")
        self._style_result_text()

    def _set_status(self, text):
        self.status_label.configure(text=text)

    # ----- i18n ----------------------------------------------------------
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
        if self.corrected_window is not None and self.corrected_window.winfo_exists():
            self.corrected_window.title(self._t("corrected_title"))
