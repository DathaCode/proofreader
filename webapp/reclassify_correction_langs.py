# -*- coding: utf-8 -*-
"""
reclassify_correction_langs.py — one-time maintenance script.

Corrections saved before the per-language self-learning feature (the `lang`
column added in corrections_db.py) all lived in one shared, untagged table.
When that column was added, every pre-existing row was defaulted to
lang='si' — a documented backfill *assumption* that the DB had been
Sinhala-only up to that point. In practice it wasn't: Tamil (and possibly
English) corrections were already being saved too, just inert, since the
old proofreading code only ever queried the DB for Sinhala text. Those rows
are now sitting under the wrong language tag in the admin panel and are
invisible to Tamil/English few-shot injection.

This retags every row by the actual Unicode script of its `wrong` text —
the same detector (`lang_detect.detect_language`) the app already uses to
route proofreading requests, so the classification is consistent with how
the rest of the system decides "what language is this text".

Run once, inside the container that owns the live corrections.db:
    docker exec proofreader-web python3 reclassify_correction_langs.py

Safe to re-run: it only touches rows whose current `lang` disagrees with
what the text's script says, and does the same deterministic detection
every time.
"""

from web_config import CORRECTIONS_PATH
from corrections_db import CorrectionsDB
from lang_detect import detect_language


def main():
    db = CorrectionsDB(CORRECTIONS_PATH)
    rows = db.data["corrections"]
    changed = 0
    for r in rows:
        current = r.get("lang") or "si"
        true_lang = detect_language(r["wrong"], default=current)
        if true_lang != current:
            print("%s: %r  (%s -> %s)" % (r["id"], r["wrong"], current, true_lang))
            db.retag_lang(r["id"], true_lang)
            changed += 1
    print("Reclassified %d / %d corrections." % (changed, len(rows)))
    db.close()


if __name__ == "__main__":
    main()
