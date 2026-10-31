# -*- coding: utf-8 -*-
"""
widgets.py — reusable UI components and font helpers for the Sinhala Proofreader.
"""

import customtkinter as ctk
import tkinter.font as tkfont

_PREFERRED_FONTS = ["Iskoola Pota", "Noto Sans Sinhala", "Nirmala UI"]
_resolved_family = None


def sinhala_family():
    """Pick the best available Sinhala font family (cached). Needs a live root."""
    global _resolved_family
    if _resolved_family is None:
        try:
            available = set(tkfont.families())
        except Exception:
            available = set()
        _resolved_family = next(
            (f for f in _PREFERRED_FONTS if f in available), _PREFERRED_FONTS[0]
        )
    return _resolved_family


_UI_FONTS = ["Nirmala UI", "Segoe UI"]
_resolved_ui = None


def ui_family():
    """Font for buttons/labels: Nirmala UI has Sinhala AND Segoe-style Latin, so
    English UI text no longer renders in Iskoola Pota's serif Latin glyphs."""
    global _resolved_ui
    if _resolved_ui is None:
        try:
            available = set(tkfont.families())
        except Exception:
            available = set()
        _resolved_ui = next((f for f in _UI_FONTS if f in available), None) or sinhala_family()
    return _resolved_ui


def font(size=16, bold=False):
    """UI (chrome) font."""
    return (ui_family(), size, "bold") if bold else (ui_family(), size)


def text_font(size=16, bold=False):
    """Font for the Sinhala text the user reads and edits (unchanged since v4)."""
    return (sinhala_family(), size, "bold") if bold else (sinhala_family(), size)


# Colours (shared with the highlight tags).
SPELL_BG = "#CC0000"
GRAMMAR_BG = "#CC6600"
OK_GREEN = "#00AA00"
ERR_RED = "#CC0000"


class StatusIndicator(ctk.CTkLabel):
    """A ✅ / ❌ connection-status label."""

    def __init__(self, master, **kw):
        super().__init__(master, text="", anchor="w", **kw)

    def set_status(self, connected, message):
        icon = "✅" if connected else "❌"
        self.configure(text="%s %s" % (icon, message),
                       text_color=OK_GREEN if connected else ERR_RED)


def confidence_badge(conf):
    """Return a short label like '90%+' for an error's confidence."""
    pct = int(round(conf * 100))
    if pct >= 90:
        return "90%+"
    if pct >= 70:
        return "70%+"
    return "<70%"


class ErrorRow(ctk.CTkFrame):
    """A clickable error row with icon, original→correction, and a confidence badge."""

    def __init__(self, master, error, on_click=None, **kw):
        super().__init__(master, fg_color="transparent", corner_radius=6, **kw)
        self.error = error
        self.on_click = on_click
        self._base = "transparent"
        self._hover = "gray25"

        is_spell = error.get("type") == "spelling"
        icon = "❌" if is_spell else "⚠️"
        tag = "SPELL" if is_spell else "GRAMMAR"
        original = error.get("original", "")
        correction = error.get("correction", "")
        arrow = "  →  %s" % correction if correction else ""
        label = "%s [%s] \"%s\"%s" % (icon, tag, original, arrow)

        self.text_label = ctk.CTkLabel(
            self, text=label, anchor="w", justify="left", font=font(14)
        )
        self.text_label.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)

        badge = ctk.CTkLabel(
            self,
            text=confidence_badge(error.get("confidence", 0.0)),
            font=font(11),
            fg_color="gray30",
            corner_radius=8,
            width=46,
        )
        badge.pack(side="right", padx=8)

        for w in (self, self.text_label):
            w.bind("<Button-1>", self._clicked)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _clicked(self, _e=None):
        if self.on_click:
            self.on_click(self.error)

    def _enter(self, _e=None):
        self.configure(fg_color=self._hover)

    def _leave(self, _e=None):
        self.configure(fg_color=self._base)


# ======================================================================
# v5 widgets
# ======================================================================
from . import theme as _TH  # noqa: E402  (after the v4 helpers above)


class Pill(ctk.CTkLabel):
    """Rounded status chip, e.g. the connection indicator in the header."""

    KINDS = {
        "ok":      (_TH.SUCCESS_SOFT, _TH.SUCCESS_TEXT, "●"),
        "bad":     (_TH.DANGER_SOFT, _TH.DANGER_TEXT, "●"),
        "warn":    (_TH.WARNING_SOFT, _TH.WARNING_TEXT, "●"),
        "info":    (_TH.ACCENT_SOFT, _TH.ACCENT_TEXT, "●"),
        "neutral": (_TH.NEUTRAL, _TH.MUTED, "○"),
    }

    def __init__(self, master, **kw):
        super().__init__(master, text="", corner_radius=12, padx=12, height=28,
                         font=font(12, True), **kw)
        self.set("neutral", "")

    def set(self, kind, text):
        bg, fg, dot = self.KINDS.get(kind, self.KINDS["neutral"])
        self.configure(text="%s  %s" % (dot, text), fg_color=bg, text_color=fg)


class Banner(ctk.CTkFrame):
    """A full-width message strip (offline / update / errors) with an optional
    action button and a close button. Hidden until show() is called."""

    KINDS = {
        "danger": (_TH.DANGER_SOFT, _TH.DANGER_TEXT, "⚠"),
        "warn":   (_TH.WARNING_SOFT, _TH.WARNING_TEXT, "⚠"),
        "info":   (_TH.ACCENT_SOFT, _TH.ACCENT_TEXT, "ℹ"),
        "ok":     (_TH.SUCCESS_SOFT, _TH.SUCCESS_TEXT, "✓"),
    }

    def __init__(self, master, pack_opts=None, **kw):
        super().__init__(master, corner_radius=10, **kw)
        self._pack_opts = pack_opts or {}
        self._action = None
        self.icon = ctk.CTkLabel(self, text="", font=font(15, True), width=22)
        self.icon.pack(side="left", padx=(14, 6), pady=8)
        self.label = ctk.CTkLabel(self, text="", font=font(13), anchor="w", justify="left")
        self.label.pack(side="left", fill="x", expand=True, pady=8)
        self.close_btn = ctk.CTkButton(self, text="✕", width=28, height=28, corner_radius=8,
                                       fg_color="transparent", hover_color=_TH.NEUTRAL_HOVER,
                                       command=self.hide)
        self.close_btn.pack(side="right", padx=(4, 8))
        self.action_btn = ctk.CTkButton(self, text="", height=30, corner_radius=8,
                                        font=font(12, True), command=self._run_action)
        self.visible = False
        self.kind = None

    def show(self, kind, text, action_text=None, action=None, closable=True):
        bg, fg, icon = self.KINDS.get(kind, self.KINDS["info"])
        self.kind = kind
        self.configure(fg_color=bg)
        self.icon.configure(text=icon, text_color=fg)
        self.label.configure(text=text, text_color=fg)
        self._action = action
        # Re-pack right-side buttons in a fixed order (close is right-most), so
        # repeated show() calls with different options never depend on old state.
        self.action_btn.pack_forget()
        self.close_btn.pack_forget()
        if closable:
            self.close_btn.pack(side="right", padx=(4, 8))
        if action_text and action:
            self.action_btn.configure(text=action_text, fg_color=fg, hover_color=fg,
                                      text_color=("#ffffff", "#111827"))
            self.action_btn.pack(side="right", padx=(4, 4 if closable else 10))
        if not self.visible:
            self.pack(**self._pack_opts)
            self.visible = True

    def hide(self):
        if self.visible:
            self.pack_forget()
            self.visible = False
            self.kind = None

    def wrap(self, width):
        self.label.configure(wraplength=max(200, width - 260))

    def _run_action(self):
        if self._action:
            self._action()


class IssueRow(ctk.CTkFrame):
    """One issue: type chip, “wrong → correct”, explanation, Accept / Ignore."""

    def __init__(self, master, error, lang="en", labels=None, on_accept=None,
                 on_ignore=None, on_focus=None, **kw):
        super().__init__(master, corner_radius=10, fg_color=_TH.CARD_BG,
                         border_width=1, border_color=_TH.BORDER, **kw)
        self.error = error
        labels = labels or {}
        is_spell = error.get("type") == "spelling"
        chip_bg, chip_fg = ((_TH.DANGER_SOFT, _TH.DANGER_TEXT) if is_spell
                            else (_TH.WARNING_SOFT, _TH.WARNING_TEXT))
        kind = {"spelling": labels.get("spelling", "Spelling"),
                "grammar": labels.get("grammar", "Grammar"),
                "grammar_discord": labels.get("grammar", "Grammar"),
                "encoding_error": labels.get("encoding", "Encoding")}.get(
            error.get("type"), labels.get("spelling", "Spelling"))
        if error.get("source") == "human_db":
            kind = labels.get("learned", "Learned")

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=kind, font=font(11, True), fg_color=chip_bg,
                     text_color=chip_fg, corner_radius=8, width=76, height=24).grid(
            row=0, column=0, rowspan=2, padx=(10, 10), pady=8, sticky="w")

        original = error.get("original", "")
        correction = error.get("correction", "")
        line = ctk.CTkFrame(self, fg_color="transparent")
        line.grid(row=0, column=1, sticky="w", pady=(8, 0))
        ctk.CTkLabel(line, text=original, font=text_font(15), text_color=_TH.DANGER_TEXT).pack(side="left")
        if correction:
            ctk.CTkLabel(line, text="  →  ", font=font(14), text_color=_TH.MUTED).pack(side="left")
            ctk.CTkLabel(line, text=correction, font=text_font(15, True),
                         text_color=_TH.SUCCESS_TEXT).pack(side="left")
        expl = (error.get("explanation_si") if lang == "si" else error.get("explanation_en")) \
            or error.get("explanation_en") or error.get("explanation_si") or ""
        self.expl = ctk.CTkLabel(self, text=expl, font=font(12), text_color=_TH.MUTED,
                                 anchor="w", justify="left", wraplength=700)
        self.expl.grid(row=1, column=1, sticky="w", pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=0, column=2, rowspan=2, padx=10)
        can_accept = bool(correction) and error.get("start") is not None
        self.accept_btn = ctk.CTkButton(
            btns, text=labels.get("accept", "Accept"), width=86, height=30, corner_radius=8,
            font=font(12, True), fg_color=_TH.SUCCESS, hover_color=_TH.SUCCESS_HOVER,
            state="normal" if can_accept else "disabled",
            command=lambda: on_accept and on_accept(error))
        self.accept_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text=labels.get("ignore", "Ignore"), width=76, height=30,
                      corner_radius=8, font=font(12), fg_color=_TH.NEUTRAL,
                      hover_color=_TH.NEUTRAL_HOVER, text_color=_TH.TEXT,
                      command=lambda: on_ignore and on_ignore(error)).pack(side="left")

        if on_focus:
            for w in (self, line, self.expl) + tuple(line.winfo_children()):
                w.bind("<Button-1>", lambda _e: on_focus(error))
                try:
                    w.configure(cursor="hand2")
                except Exception:
                    pass

    def set_wrap(self, width):
        self.expl.configure(wraplength=max(240, width - 330))


# ----------------------------------------------------------------------
# SinhalaText — a fast editor for LONG Sinhala text
# ----------------------------------------------------------------------
# Tk's text widget wraps a line by re-measuring the REST of the current text
# segment for every display line. With Sinhala (complex-script shaping) that is
# O(n^2) per paragraph: a 500-word paragraph took ~3.5 s to show and ~2.5 s per
# KEYSTROKE; 2,000 words took over two minutes (CTkTextbox is ~4x slower still,
# and forces a full re-measure on every insert).
#
# Fix: split each paragraph into short segments with invisible, style-less tags
# every 2 words (cut only at spaces, so shaping/conjuncts are never broken). The
# text itself is untouched. Measured: 5,000 words load in <1 s, ~0.1 s/keystroke.
import re as _re  # noqa: E402
import tkinter as _tk  # noqa: E402

_WORD_RE = _re.compile(r"\S+")
_SEG_TAGS = ("_seg0", "_seg1")


def editor_colors():
    """Editor colours, matching CTkTextbox's theme (so the voice button blends in)."""
    try:
        bg = ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]
        bg = bg[0] if ctk.get_appearance_mode() == "Light" else bg[1]
    except Exception:
        bg = "#1d1e1e" if ctk.get_appearance_mode() == "Dark" else "#f9f9fa"
    if ctk.get_appearance_mode() == "Dark":
        return {"bg": bg, "fg": "#e8edf4", "insert": "#e8edf4", "sel": "#2b5cab"}
    return {"bg": bg, "fg": "#1f2733", "insert": "#1f2733", "sel": "#bcd3f5"}


def clipboard_text(widget):
    """Clipboard text WITHOUT corruption. Plain `clipboard get` (tkinter's
    clipboard_get) decodes Tk's internal ~4 KB chunks one by one, so when this
    app itself put long Sinhala text on the clipboard a character can be cut in
    half at a chunk edge ("ලංකාවේ" -> "ලංකà·වේ"). Ask for UTF8_STRING first,
    exactly like Tk's own paste does. Returns "" if there is nothing."""
    for kw in ({"type": "UTF8_STRING"}, {}):
        try:
            return widget.selection_get(selection="CLIPBOARD", **kw)
        except _tk.TclError:
            continue
    return ""


def segment_text(text, first_line=1, last_line=None, words=2):
    """(Re)apply segment tags to lines first_line..last_line of a tk.Text."""
    if last_line is None:
        last_line = int(text.index("end-1c").split(".")[0])
    for line in range(max(1, first_line), last_line + 1):
        s = text.get("%d.0" % line, "%d.end" % line)
        text.tag_remove(_SEG_TAGS[0], "%d.0" % line, "%d.end" % line)
        text.tag_remove(_SEG_TAGS[1], "%d.0" % line, "%d.end" % line)
        starts = [m.start() for m in _WORD_RE.finditer(s)]
        if len(starts) <= words:
            continue
        ranges = ([], [])
        for k, i in enumerate(range(0, len(starts), words)):
            a = starts[i]
            b = starts[i + words] if i + words < len(starts) else len(s)
            ranges[k & 1].extend(("%d.%d" % (line, a), "%d.%d" % (line, b)))
        for tag, r in zip(_SEG_TAGS, ranges):
            if r:
                text.tag_add(tag, *r)


class SinhalaText(ctk.CTkFrame):
    """A rounded, themed frame holding a fast tk.Text (`.text`) + scrollbar.

    Re-segments automatically after typing pauses and after paste; call
    segment_all() after inserting text programmatically."""

    def __init__(self, master, font_spec=None, readonly=False, **kw):
        super().__init__(master, corner_radius=_TH.R_BOX, border_width=1,
                         border_color=_TH.BORDER, **kw)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.text = _tk.Text(self, wrap="word", relief="flat", borderwidth=0,
                             highlightthickness=0, padx=10, pady=8, font=font_spec,
                             undo=not readonly, autoseparators=True, maxundo=-1)
        self.text.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)
        bar = ctk.CTkScrollbar(self, command=self.text.yview)
        bar.grid(row=0, column=1, sticky="ns", padx=(0, 3), pady=5)
        self.text.configure(yscrollcommand=bar.set)
        self._job = None
        self.after_paste = None             # optional callback after a paste
        if not readonly:
            # Widget bindings run BEFORE Tk's "Text" class binding (which does the
            # actual paste), so hook a tag placed AFTER it: segmentation then runs
            # synchronously on the pasted text, before Tk's first redraw.
            post = "SinhalaTextPost%d" % id(self)
            tags = list(self.text.bindtags())
            tags.insert(tags.index("Text") + 1, post)
            self.text.bindtags(tuple(tags))
            for seq in ("<<Undo>>", "<<Redo>>"):
                self.text.bind_class(post, seq, lambda _e: self.segment_all())
            self.text.bind_class(post, "<<Cut>>", lambda _e: self._segment_insert_line())
            # Paste is handled HERE (and Tk's own paste skipped): Tk's version
            # inserts plain text and immediately calls `see insert`, which lays
            # out the whole unsegmented paragraph — seconds for long text.
            self.text.bind("<<Paste>>", self._paste)
            self.text.bind("<KeyRelease>", self._schedule, add="+")
        self.refresh_theme()

    def insert_text(self, index, chars):
        """Insert `chars` already split into short tagged segments (fast)."""
        t = self.text
        start = t.index(index)
        args, k = [], 0
        for line_no, line in enumerate(chars.split("\n")):
            if line_no:
                args += ["\n", ()]
            pos = [m.start() for m in _WORD_RE.finditer(line)] or [0]
            cuts = pos[::2] + [len(line)]
            if cuts[0] > 0:
                args += [line[:cuts[0]], ()]
            for a, b in zip(cuts, cuts[1:]):
                if b > a:
                    args += [line[a:b], (_SEG_TAGS[k & 1],)]
                    k += 1
        joins_before = t.get("%s linestart" % start, start) != ""
        joins_after = t.get(start, "%s lineend" % start) != ""
        if args:
            t.insert(start, *args)
        first = int(start.split(".")[0])
        last = int(t.index("%s+%dc" % (start, len(chars))).split(".")[0])
        # Only lines that merged with existing text need re-tagging.
        if joins_before:
            segment_text(t, first, first)
        if joins_after and last != first:
            segment_text(t, last, last)
        return start

    def _paste(self, _e=None):
        t = self.text
        data = clipboard_text(t)
        if not data:
            return "break"
        t.edit_separator()
        try:
            t.delete("sel.first", "sel.last")
        except _tk.TclError:
            pass                            # nothing selected
        start = self.insert_text("insert", data)
        t.edit_separator()
        # Scrolling to the END of a very long paragraph makes Tk lay out the
        # whole paragraph (seconds). After a big paste show where it STARTED.
        last_para = data.rsplit("\n", 1)[-1]
        t.see("insert" if len(last_para) < 2500 else start)
        if self.after_paste:                # "break" also stops other <<Paste>>
            self.after_idle(self.after_paste)   # handlers, so notify explicitly
        return "break"

    def refresh_theme(self):
        c = editor_colors()
        self.configure(fg_color=c["bg"])
        self.text.configure(bg=c["bg"], fg=c["fg"], insertbackground=c["insert"],
                            selectbackground=c["sel"], inactiveselectbackground=c["sel"])

    def segment_all(self):
        segment_text(self.text)

    def _segment_insert_line(self):
        line = int(self.text.index("insert").split(".")[0])
        segment_text(self.text, line, line)

    def _schedule(self, _e=None):
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = self.after(350, self._run_scheduled)

    def _run_scheduled(self):
        self._job = None
        self._segment_insert_line()
