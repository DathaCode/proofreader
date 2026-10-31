# -*- coding: utf-8 -*-
"""
history.py — the last few checks, stored on THIS PC only.

Saved to ~/.sinhala_proofreader/history.json (next to config.json) so a user can
reopen or re-copy something they checked earlier. Nothing here is sent anywhere.
"""

import os
import json
import threading
from datetime import datetime

from config import CONFIG_DIR

HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
MAX_ITEMS = 30


class History:
    def __init__(self, path=HISTORY_FILE, max_items=MAX_ITEMS):
        self.path = path
        self.max_items = max_items
        self.lock = threading.Lock()
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [d for d in data if isinstance(d, dict) and d.get("original")]
        except (OSError, ValueError):
            return []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def add(self, original, corrected, words, issues):
        """Newest first; an identical re-check replaces the older entry."""
        entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "original": original, "corrected": corrected,
                 "words": int(words), "issues": int(issues)}
        with self.lock:
            self.items = [i for i in self.items if i.get("original") != original]
            self.items.insert(0, entry)
            del self.items[self.max_items:]
            self._save()

    def remove(self, index):
        with self.lock:
            if 0 <= index < len(self.items):
                del self.items[index]
                self._save()

    def clear(self):
        with self.lock:
            self.items = []
            self._save()
