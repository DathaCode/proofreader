# -*- coding: utf-8 -*-
"""
usage_logger.py — thread-safe CSV usage log for the proxy server.

Records one row per /proofread request: timestamp, client IP, word count,
errors found, pre-fixed count, latency, status.
"""

import os
import csv
import threading
from datetime import datetime
from collections import defaultdict

HEADER = ["timestamp", "client_ip", "words", "errors_found",
          "pre_fixed", "latency_ms", "status"]


class UsageLogger:
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        if not os.path.exists(log_path):
            with open(log_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(HEADER)

    def log(self, client_ip, words, errors_found, pre_fixed, latency_ms, status):
        row = [datetime.now().isoformat(), client_ip, words, errors_found,
               pre_fixed, latency_ms, status]
        with self.lock:
            with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)

    def read_rows(self, limit=500):
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            return rows[-limit:][::-1]  # newest first
        except OSError:
            return []

    def daily_totals(self):
        totals = defaultdict(lambda: {"requests": 0, "words": 0, "errors": 0})
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    day = (r.get("timestamp", "")[:10]) or "?"
                    t = totals[day]
                    t["requests"] += 1
                    t["words"] += int(r.get("words") or 0)
                    t["errors"] += int(r.get("errors_found") or 0)
        except OSError:
            pass
        return dict(sorted(totals.items(), reverse=True))

    def summary(self):
        rows = 0
        words = 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows += 1
                    words += int(r.get("words") or 0)
        except OSError:
            pass
        return {"total_requests": rows, "total_words": words}
