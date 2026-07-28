# -*- coding: utf-8 -*-
"""
welcome_dialog.py — friendly first-run dialog shown when no API key is saved.
"""

import customtkinter as ctk

from .widgets import font


class WelcomeDialog(ctk.CTkToplevel):
    def __init__(self, master, on_add_key=None, on_skip=None):
        super().__init__(master)
        self.on_add_key = on_add_key
        self.on_skip = on_skip

        self.title("Welcome")
        self.geometry("460x300")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="👋 Welcome to Sinhala Proofreader!",
            font=font(20, True),
            justify="center",
        ).pack(pady=(26, 10))

        ctk.CTkLabel(
            self,
            text="This app needs a Gemini API key to work.\nYou can get one for free.",
            font=font(14),
            justify="center",
        ).pack(pady=(0, 20))

        ctk.CTkButton(
            self,
            text="🔑 Add API Key (Recommended)",
            command=self._add_key,
        ).pack(fill="x", padx=40, pady=6)

        ctk.CTkButton(
            self,
            text="⏭️ Later",
            fg_color="gray40",
            hover_color="gray30",
            command=self._skip,
        ).pack(fill="x", padx=40, pady=6)

        self.after(120, self.lift)

    def _add_key(self):
        self.destroy()
        if self.on_add_key:
            self.on_add_key()

    def _skip(self):
        self.destroy()
        if self.on_skip:
            self.on_skip()
