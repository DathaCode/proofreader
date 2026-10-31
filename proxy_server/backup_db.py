# -*- coding: utf-8 -*-
"""
backup_db.py — nightly backup of the Control PC DB files to Amazon S3.

What it does (Windows, no extra pip packages — stdlib only + AWS CLI):
  1. Takes CONSISTENT snapshots of data/corrections.db and data/usage.db using
     SQLite's online backup API (safe even while the proxy has them open).
  2. Stages those snapshots + usage_log.csv (+ proxy_config.json) — NEVER the
     api_key.txt secret.
  3. Uploads the staging folder to  s3://<bucket>/<prefix>/<YYYY-MM-DD>/
     using the AWS CLI (`aws s3 cp --recursive`).
  4. Prunes snapshot day-folders older than `retention_days`.

Settings live in  backup_config.json  (edit it once, like api_key.txt).
Run it via  BACKUP_S3.bat  (manually or from Task Scheduler).
"""

import os
import sys
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "backup_config.json")
LOG_PATH = os.path.join(BASE_DIR, "backup.log")
STAGING_DIR = os.path.join(BASE_DIR, "_backup_staging")

CORRECTIONS_DB = os.path.join(DATA_DIR, "corrections.db")
USAGE_DB = os.path.join(DATA_DIR, "usage.db")            # v5+: usage logs + client names
USAGE_LOG = os.path.join(DATA_DIR, "usage_log.csv")      # v4 log (kept if present)
PROXY_CONFIG = os.path.join(BASE_DIR, "proxy_config.json")

PLACEHOLDER = "REPLACE_WITH_YOUR_BUCKET"

DEFAULTS = {
    "s3_bucket": PLACEHOLDER,
    "s3_prefix": "lan-proxy-backups",
    "aws_region": "",          # blank = use the AWS CLI's configured default
    "retention_days": 30,      # 0 = keep everything (no pruning)
    "include_proxy_config": True,
    "aws_cli": "",             # blank = auto-detect (aws on PATH, else Program Files)
}


def log(msg):
    line = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (FileNotFoundError, ValueError):
        pass
    return cfg


def find_aws(cli_hint):
    if cli_hint and os.path.exists(cli_hint):
        return cli_hint
    found = shutil.which("aws")
    if found:
        return found
    for p in (r"C:\Program Files\Amazon\AWSCLIV2\aws.exe",
              r"C:\Program Files (x86)\Amazon\AWSCLIV2\aws.exe"):
        if os.path.exists(p):
            return p
    return None


def snapshot_sqlite(src_path, dst_path):
    """Consistent copy of an open SQLite DB via the online backup API."""
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def stage_files(cfg):
    if os.path.isdir(STAGING_DIR):
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    os.makedirs(STAGING_DIR, exist_ok=True)

    staged = []
    if os.path.exists(CORRECTIONS_DB):
        snapshot_sqlite(CORRECTIONS_DB, os.path.join(STAGING_DIR, "corrections.db"))
        staged.append("corrections.db")
    else:
        log("WARNING: corrections.db not found (nothing learned yet?)")

    if os.path.exists(USAGE_DB):
        snapshot_sqlite(USAGE_DB, os.path.join(STAGING_DIR, "usage.db"))
        staged.append("usage.db")

    if os.path.exists(USAGE_LOG):
        shutil.copy2(USAGE_LOG, os.path.join(STAGING_DIR, "usage_log.csv"))
        staged.append("usage_log.csv")

    if cfg["include_proxy_config"] and os.path.exists(PROXY_CONFIG):
        shutil.copy2(PROXY_CONFIG, os.path.join(STAGING_DIR, "proxy_config.json"))
        staged.append("proxy_config.json")

    return staged


def aws_base(aws, cfg):
    cmd = [aws]
    if cfg["aws_region"]:
        cmd += ["--region", cfg["aws_region"]]
    return cmd


def upload(aws, cfg, day):
    dest = "s3://%s/%s/%s/" % (cfg["s3_bucket"], cfg["s3_prefix"].strip("/"), day)
    cmd = aws_base(aws, cfg) + ["s3", "cp", STAGING_DIR, dest, "--recursive"]
    log("Uploading -> %s" % dest)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("aws s3 cp failed: %s" % (r.stderr.strip() or r.stdout.strip())[:400])
    return dest


def prune(aws, cfg):
    days = int(cfg["retention_days"] or 0)
    if days <= 0:
        return
    base = "s3://%s/%s/" % (cfg["s3_bucket"], cfg["s3_prefix"].strip("/"))
    r = subprocess.run(aws_base(aws, cfg) + ["s3", "ls", base],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("Prune skipped (could not list %s): %s" % (base, r.stderr.strip()[:200]))
        return
    cutoff = (datetime.now() - timedelta(days=days)).date()
    removed = 0
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "PRE":
            name = parts[1].rstrip("/")
            try:
                d = datetime.strptime(name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < cutoff:
                subprocess.run(aws_base(aws, cfg) +
                               ["s3", "rm", base + name + "/", "--recursive"],
                               capture_output=True, text=True)
                removed += 1
    if removed:
        log("Pruned %d snapshot(s) older than %d days" % (removed, days))


def main():
    cfg = load_config()

    if cfg["s3_bucket"] == PLACEHOLDER or not cfg["s3_bucket"]:
        log("SETUP NEEDED: open backup_config.json and set \"s3_bucket\" "
            "(and s3_prefix / aws_region). Aborting.")
        return 1

    aws = find_aws(cfg["aws_cli"])
    if not aws:
        log("ERROR: AWS CLI not found. Install AWS CLI v2 and run `aws configure`, "
            "or set \"aws_cli\" in backup_config.json to aws.exe's full path.")
        return 1

    try:
        staged = stage_files(cfg)
        if not staged:
            log("Nothing to back up.")
            return 1
        day = datetime.now().strftime("%Y-%m-%d")
        dest = upload(aws, cfg, day)
        prune(aws, cfg)
        log("BACKUP OK: %s (%s)" % (dest, ", ".join(staged)))
        return 0
    except Exception as e:
        log("BACKUP FAILED: %s" % e)
        return 1
    finally:
        shutil.rmtree(STAGING_DIR, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
