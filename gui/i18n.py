# -*- coding: utf-8 -*-
"""
i18n.py — tiny translation table for the GUI.

t(lang, key) returns the string for "en" or "si"; falls back to English, then
to the key itself. Used so the UI Language setting actually switches the app.
"""

STRINGS = {
    # window / header
    "app_title":     {"en": "🔤  Sinhala Word & Grammar Checker", "si": "🔤  සිංහල වචන හා ව්‍යාකරණ පරීක්ෂකය"},
    "app_subtitle":  {"en": "Sinhala Proofreader", "si": "සිංහල වචන පරීක්ෂකය"},
    "settings_btn":  {"en": "⚙️ Settings", "si": "⚙️ සැකසීම්"},

    # mode bar
    "api_key_btn":   {"en": "🔑 API Key", "si": "🔑 API යතුර"},
    "lan_mode":      {"en": "LAN mode", "si": "LAN ආකාරය"},
    "key_ready":     {"en": "API key set (ready)", "si": "API යතුර සකසා ඇත (සූදානම්)"},
    "key_missing":   {"en": "No API key — Settings", "si": "API යතුරක් නැත — සැකසීම්"},

    # input panel
    "input_label":   {"en": "📝 Enter your text  (Input)", "si": "📝 ඔබේ පාඨය ඇතුළු කරන්න  (Input)"},
    "check_btn":     {"en": "🔍 Check  (Ctrl+Enter)", "si": "🔍 පරීක්ෂා කරන්න  (Ctrl+Enter)"},
    "checking_btn":  {"en": "⏳ Checking...", "si": "⏳ පරීක්ෂා කරමින්..."},
    "clear_btn":     {"en": "🗑️ Clear", "si": "🗑️ හිස් කරන්න"},
    "errors_label":  {"en": "Errors Found", "si": "දෝෂ ලැයිස්තුව"},

    # results panel
    "results_label": {"en": "🔍 Results  —  🟥 spelling   🟧 grammar", "si": "🔍 ප්‍රතිඵල  —  🟥 spelling   🟧 grammar"},
    "corrected_label": {"en": "✅ Corrected Text", "si": "✅ නිවැරදි කළ පාඨය"},
    "open_corrected": {"en": "✅ Open Corrected Text", "si": "✅ නිවැරදි කළ පාඨය විවෘත කරන්න"},
    "apply_all":     {"en": "✨ Apply All Fixes", "si": "✨ සියලු නිවැරදි කිරීම් යොදන්න"},
    "applied_all":   {"en": "✅ Applied all fixes to the input", "si": "✅ සියලු නිවැරදි කිරීම් පාඨයට යෙදුවා"},
    "results_hint":  {"en": "💡 Click a highlighted word to see its fix.",
                      "si": "💡 නිවැරදි කිරීම බැලීමට ඉස්මතු කළ වචනයක් ක්ලික් කරන්න."},
    "input_hint":    {"en": "Paste or type Sinhala text, then press Check (Ctrl+Enter).",
                      "si": "සිංහල පාඨය ඇලවීම් හෝ ටයිප් කර, Check (Ctrl+Enter) ඔබන්න."},
    "corrected_title": {"en": "Corrected Text — Sinhala Proofreader", "si": "නිවැරදි කළ පාඨය — සිංහල වචන පරීක්ෂකය"},
    "corrected_hint": {"en": "Edit the text below, then Save My Corrections to teach the app.",
                       "si": "පහත පාඨය සංස්කරණය කර, යෙදුමට උගැන්වීමට \"නිවැරදිකිරීම් සුරකින්න\" ඔබන්න."},
    "close_btn":     {"en": "Close", "si": "වසන්න"},
    "copy_btn":      {"en": "📋 Copy Corrected", "si": "📋 පිටපත් කරන්න"},
    "export_btn":    {"en": "💾 Export Report", "si": "💾 වාර්තාව"},
    "save_corr_btn": {"en": "✍️ Save My Corrections", "si": "✍️ නිවැරදිකිරීම් සුරකින්න"},

    # status messages
    "ready":         {"en": "Ready", "si": "සූදානම්"},
    "enter_text":    {"en": "📝 Please enter some text", "si": "📝 කරුණාකර පාඨය ඇතුළු කරන්න"},
    "need_key":      {"en": "🔑 A Gemini API key is required — opening Settings", "si": "🔑 Gemini API යතුරක් අවශ්‍යයි — සැකසීම් විවෘත වෙමින්"},
    "checking_direct": {"en": "⏱️ Checking with Gemini...", "si": "⏱️ Gemini සමඟ පරීක්ෂා කරමින්..."},
    "checking_lan":  {"en": "⏱️ Checking via Control PC...", "si": "⏱️ Control PC සමඟ පරීක්ෂා කරමින්..."},
    "no_errors":     {"en": "✅ No errors found", "si": "✅ දෝෂ හමු නොවීය"},
    "no_errors_row": {"en": "✅ No errors found", "si": "✅ දෝෂ හමු නොවීය  (no errors found)"},
    "settings_saved": {"en": "Settings saved", "si": "සැකසීම් සුරැකිණි"},
    "nothing_copy":  {"en": "Nothing to copy", "si": "පිටපත් කිරීමට කිසිවක් නැත"},
    "copied":        {"en": "📋 Corrected text copied", "si": "📋 නිවැරදි කළ පාඨය පිටපත් විය"},
    "run_first":     {"en": "Run a check first", "si": "මුලින් පරීක්ෂා කරන්න"},
    "no_edits":      {"en": "✅ No edits — nothing to learn", "si": "✅ වෙනස්කම් නොමැත"},
    "saved_local":   {"en": "✅ %d correction(s) saved to local DB", "si": "✅ නිවැරදිකිරීම් %d ක් local DB වෙත සුරකිණා"},
    "saved_proxy":   {"en": "✅ %d correction(s) saved to Control PC", "si": "✅ නිවැරදිකිරීම් %d ක් Control PC වෙත සුරකිණා"},

    # totals
    "total_errors":  {"en": "Total: %d errors", "si": "මුළු දෝෂ: %d"},

    # ===== settings dialog =====
    "set_title":     {"en": "⚙️ Settings", "si": "⚙️ සැකසීම්"},
    "set_save":      {"en": "💾 Save", "si": "💾 සුරකින්න"},
    "set_cancel":    {"en": "Cancel", "si": "අවලංගු කරන්න"},
    "set_conn_mode": {"en": "🌐 Connection Mode", "si": "🌐 සම්බන්ධතා ආකාරය"},
    "set_mode_direct": {"en": "● Direct — API key on this PC (Online)",
                        "si": "● සෘජු — මෙම PC එකේ API යතුර (අන්තර්ජාලය)"},
    "set_mode_lan":  {"en": "● LAN Proxy — via Control PC (no key needed here)",
                      "si": "● LAN ප්‍රොක්සි — Control PC හරහා (යතුරක් අවශ්‍ය නැත)"},
    "set_api_key":   {"en": "🔑 Gemini API Key", "si": "🔑 Gemini API යතුර"},
    "set_test_conn": {"en": "Test Connection", "si": "සම්බන්ධතාව පරීක්ෂා කරන්න"},
    "set_testing":   {"en": "⏳ Checking...", "si": "⏳ පරීක්ෂා කරමින්..."},
    "set_key_empty": {"en": "Enter a key, then Save", "si": "යතුර ඇතුළු කර Save කරන්න"},
    "set_help_title": {"en": "🔗 How to get a key", "si": "🔗 API යතුරක් ලබා ගන්නේ කෙසේද?"},
    "set_help_steps": {"en": "1. Go to aistudio.google.com\n2. Click \"Get API Key\"\n3. Copy the key and paste it here",
                       "si": "1. aistudio.google.com වෙත යන්න\n2. \"Get API Key\" ක්ලික් කරන්න\n3. යතුර copy කර මෙහි paste කරන්න"},
    "set_open_aistudio": {"en": "🌐 Open aistudio.google.com", "si": "🌐 aistudio.google.com විවෘත කරන්න"},
    "set_model":     {"en": "Gemini Model:", "si": "Gemini ආකෘතිය:"},
    "model_fast":    {"en": "Fast, Free — Recommended", "si": "වේගවත්, නොමිලේ — නිර්දේශිතයි"},
    "model_latest":  {"en": "Always newest flash", "si": "සැම විට අලුත්ම flash"},
    "model_pro":     {"en": "Best quality, low free quota", "si": "හොඳම ගුණත්වය, අඩු නොමිලේ සීමාව"},
    "set_proxy_url": {"en": "Control PC URL:", "si": "Control PC ලිපිනය:"},
    "set_test_proxy": {"en": "📡 Test Proxy Connection", "si": "📡 ප්‍රොක්සි සම්බන්ධතාව පරීක්ෂා කරන්න"},
    "set_proxy_hint": {"en": "No API key needed on this PC — it works through the Control PC.",
                       "si": "මෙම PC එකේ API යතුරක් අවශ්‍ය නැත — Control PC හරහා ක්‍රියා කරයි."},
    "set_proxy_empty": {"en": "Enter a Proxy URL", "si": "Proxy URL ඇතුළත් කරන්න"},
    "set_theme":     {"en": "Theme:", "si": "තේමාව:"},
    "set_theme_dark": {"en": "Dark", "si": "අඳුරු"},
    "set_theme_light": {"en": "Light", "si": "ආලෝකමත්"},
    "set_lang":      {"en": "UI Language:", "si": "අතුරුමුහුණත් භාෂාව:"},
}


def t(lang, key, *args):
    entry = STRINGS.get(key, {})
    s = entry.get(lang) or entry.get("en") or key
    if args:
        try:
            return s % args
        except Exception:
            return s
    return s
