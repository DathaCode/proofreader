/* i18n.js — UI translations (English / Sinhala / Tamil) + language switcher.
 *
 * Usage in HTML:
 *   <span data-i18n="check_btn"></span>          -> textContent
 *   <textarea data-i18n-ph="input_placeholder">  -> placeholder
 *   <button data-i18n-title="theme">             -> title attribute
 *   <button data-lang-btn="si">සිං</button>       -> switcher button
 *
 * In JS: t("errors_found", 3)  ->  "3 errors found" (%s/%d substituted in order)
 * Fires a "langchange" event so pages can re-render dynamic content.
 */

window.I18N = {
  en: {
    app_name: "AI Proofreader",
    logout: "Logout", admin_link: "Admin", proofreader_link: "Proofreader",
    theme: "Theme",
    nav_proofreader: "Proofreader", nav_history: "History",
    nav_profile: "Profile", nav_admin: "Admin",
    login_sub: "Sinhala · Tamil · English Proofreader",
    username_label: "Username", password_label: "Password", login_btn: "Sign in →",
    email_label: "Email", fullname_label: "Full name", confirm_label: "Confirm password",
    reg_title: "Create account", reg_btn: "Create account", reg_done: "Registered",
    reg_pending: "Your account is awaiting administrator approval. You'll be able to sign in once approved.",
    reg_ready: "Your account is ready — you can sign in now.",
    no_account: "No account?", register_link: "Register",
    have_account: "Already have an account?", login_link: "Sign in",
    change_password: "Change password", current_password: "Current password",
    new_password: "New password", edit_profile: "Edit profile",
    save_btn_generic: "Save changes", active_sessions: "Active sessions",
    stat_role: "Role", stat_logins: "Logins", stat_proofreads: "Proofreads",
    stat_member_since: "Member since", no_history: "No proofreadings yet.",
    col_time: "Time", col_lang: "Lang", col_text: "Text",
    col_words: "Words", col_errors: "Errors", col_status: "Status",

    input_heading: "Input text",
    input_placeholder: "Enter your text here...",
    check_btn: "✅ Check",
    clear_btn: "🗑️ Clear",
    text_lang_label: "Text language",
    lang_auto: "Auto-detect",
    detected_as: "Detected: %s",

    results_heading: "Results",
    highlighted_label: "Highlighted text",
    corrected_label: "Corrected text (editable)",
    corrected_placeholder: "Corrected text appears here…",
    results_placeholder: "Results appear here…",
    copy_btn: "📋 Copy",
    save_btn: "✍️ Save my corrections",
    errorlist_heading: "Error list",
    errors_placeholder: "Enter text and press Check.",
    loading_msg: "Checking with Gemini...",

    counter: "%s words · %s chars",

    lang_si: "Sinhala", lang_ta: "Tamil", lang_en: "English",
    type_spelling: "spelling", type_grammar: "grammar",
    type_grammar_discord: "grammar", type_punctuation: "punctuation",
    type_encoding_error: "encoding",

    enter_text: "Please enter some text",
    conn_error: "Connection error",
    copied: "Copied 📋",
    nothing_copy: "Nothing to copy",
    no_changes: "No changes found",
    saved_n: "%s correction(s) saved",
    no_errors: "No errors ✅",
    errors_found: "%s error(s) found",
    rate_limited: "Rate limit exceeded — try again in a minute.",
    save_nothing: "Nothing to save",
    check_first: "Check some text first",
    confirm_save: "Save these %s correction(s)?",
    save_failed: "Save failed",

    // login
    login_title: "Sign in",
    login_sub: "Sinhala · Tamil · English Proofreader",
    username_label: "Username",
    password_label: "Password",
    login_btn: "Sign in →",
  },

  si: {
    app_name: "AI පාඨ පරීක්ෂක",
    logout: "පිටවීම", admin_link: "පරිපාලක", proofreader_link: "පරීක්ෂක",
    theme: "තේමාව",
    nav_proofreader: "පරීක්ෂක", nav_history: "ඉතිහාසය",
    nav_profile: "පැතිකඩ", nav_admin: "පරිපාලක",
    email_label: "විද්‍යුත් තැපෑල", fullname_label: "සම්පූර්ණ නම",
    confirm_label: "මුරපදය තහවුරු කරන්න",
    reg_title: "ගිණුමක් සාදන්න", reg_btn: "ගිණුම සාදන්න", reg_done: "ලියාපදිංචි විය",
    reg_pending: "ඔබගේ ගිණුම පරිපාලක අනුමැතිය බලාපොරොත්තුවෙන් සිටී. අනුමත වූ පසු පිවිසිය හැක.",
    reg_ready: "ඔබගේ ගිණුම සූදානම් — දැන් පිවිසිය හැක.",
    no_account: "ගිණුමක් නැද්ද?", register_link: "ලියාපදිංචි වන්න",
    have_account: "දැනටමත් ගිණුමක් තිබේද?", login_link: "පිවිසෙන්න",
    change_password: "මුරපදය වෙනස් කරන්න", current_password: "වත්මන් මුරපදය",
    new_password: "නව මුරපදය", edit_profile: "පැතිකඩ සංස්කරණය",
    save_btn_generic: "වෙනස්කම් සුරකින්න", active_sessions: "සක්‍රීය සැසි",
    stat_role: "භූමිකාව", stat_logins: "පිවිසුම්", stat_proofreads: "පරීක්ෂණ",
    stat_member_since: "සාමාජික වූයේ", no_history: "තවම පරීක්ෂණ නැත.",
    col_time: "වේලාව", col_lang: "භාෂාව", col_text: "පෙළ",
    col_words: "වචන", col_errors: "දෝෂ", col_status: "තත්ත්වය",

    input_heading: "ආදාන පෙළ",
    input_placeholder: "පෙළ මෙහි ඇතුළු කරන්න...",
    check_btn: "✅ පරීක්ෂා කරන්න",
    clear_btn: "🗑️ හිස් කරන්න",
    text_lang_label: "පෙළ භාෂාව",
    lang_auto: "ස්වයංක්‍රීය",
    detected_as: "හඳුනාගත්තේ: %s",

    results_heading: "ප්‍රතිඵල",
    highlighted_label: "දෝෂ ලකුණු කළ පෙළ",
    corrected_label: "නිවැරදි කළ පෙළ (සංස්කරණය කළ හැක)",
    corrected_placeholder: "නිවැරදි කළ පෙළ මෙහි දිස්වේ…",
    results_placeholder: "ප්‍රතිඵල මෙහි දිස්වේ…",
    copy_btn: "📋 පිටපත් කරන්න",
    save_btn: "✍️ මගේ නිවැරදි කිරීම් සුරකින්න",
    errorlist_heading: "දෝෂ ලැයිස්තුව",
    errors_placeholder: "පෙළක් ඇතුළු කර පරීක්ෂා කරන්න.",
    loading_msg: "Gemini සමඟ පරීක්ෂා කරමින්...",

    counter: "%s වචන · %s අකුරු",

    lang_si: "සිංහල", lang_ta: "දෙමළ", lang_en: "ඉංග්‍රීසි",
    type_spelling: "අක්ෂර වින්‍යාස", type_grammar: "ව්‍යාකරණ",
    type_grammar_discord: "ව්‍යාකරණ", type_punctuation: "විරාම ලකුණු",
    type_encoding_error: "encoding",

    enter_text: "කරුණාකර පෙළක් ඇතුළු කරන්න",
    conn_error: "සම්බන්ධතා දෝෂයකි",
    copied: "පිටපත් කරන ලදී 📋",
    nothing_copy: "පිටපත් කිරීමට කිසිවක් නැත",
    no_changes: "වෙනස්කම් හමු නොවීය",
    saved_n: "නිවැරදි කිරීම් %s ක් සුරකින ලදී",
    no_errors: "දෝෂ නොමැත ✅",
    errors_found: "දෝෂ %s ක් හමු විය",
    rate_limited: "ඉල්ලීම් සීමාව ඉක්මවා ඇත — මිනිත්තුවකින් නැවත උත්සාහ කරන්න.",
    save_nothing: "සුරැකීමට කිසිවක් නැත",
    check_first: "පළමුව පෙළක් පරීක්ෂා කරන්න",
    confirm_save: "මෙම නිවැරදි කිරීම් %s ක් සුරකින්නද?",
    save_failed: "සුරැකීම අසාර්ථකයි",

    login_title: "පිවිසෙන්න",
    login_sub: "සිංහල · දෙමළ · ඉංග්‍රීසි පාඨ පරීක්ෂක",
    username_label: "පරිශීලක නාමය",
    password_label: "මුරපදය",
    login_btn: "පිවිසෙන්න →",
  },

  ta: {
    app_name: "AI சரிபார்ப்பான்",
    logout: "வெளியேறு", admin_link: "நிர்வாகம்", proofreader_link: "சரிபார்ப்பான்",
    theme: "தீம்",
    nav_proofreader: "சரிபார்ப்பான்", nav_history: "வரலாறு",
    nav_profile: "சுயவிவரம்", nav_admin: "நிர்வாகம்",
    email_label: "மின்னஞ்சல்", fullname_label: "முழுப் பெயர்",
    confirm_label: "கடவுச்சொல்லை உறுதிப்படுத்து",
    reg_title: "கணக்கை உருவாக்கு", reg_btn: "கணக்கை உருவாக்கு", reg_done: "பதிவு செய்யப்பட்டது",
    reg_pending: "உங்கள் கணக்கு நிர்வாகி அனுமதிக்காக காத்திருக்கிறது. அனுமதிக்கப்பட்ட பிறகு உள்நுழையலாம்.",
    reg_ready: "உங்கள் கணக்கு தயார் — இப்போது உள்நுழையலாம்.",
    no_account: "கணக்கு இல்லையா?", register_link: "பதிவு செய்க",
    have_account: "ஏற்கனவே கணக்கு உள்ளதா?", login_link: "உள்நுழைக",
    change_password: "கடவுச்சொல்லை மாற்று", current_password: "தற்போதைய கடவுச்சொல்",
    new_password: "புதிய கடவுச்சொல்", edit_profile: "சுயவிவரத்தைத் திருத்து",
    save_btn_generic: "மாற்றங்களைச் சேமி", active_sessions: "செயலில் உள்ள அமர்வுகள்",
    stat_role: "பங்கு", stat_logins: "உள்நுழைவுகள்", stat_proofreads: "சரிபார்ப்புகள்",
    stat_member_since: "உறுப்பினர் முதல்", no_history: "இன்னும் சரிபார்ப்புகள் இல்லை.",
    col_time: "நேரம்", col_lang: "மொழி", col_text: "உரை",
    col_words: "சொற்கள்", col_errors: "பிழைகள்", col_status: "நிலை",

    input_heading: "உள்ளீட்டு உரை",
    input_placeholder: "உங்கள் உரையை இங்கே உள்ளிடவும்...",
    check_btn: "✅ சரிபார்",
    clear_btn: "🗑️ அழி",
    text_lang_label: "உரை மொழி",
    lang_auto: "தானாக",
    detected_as: "கண்டறியப்பட்டது: %s",

    results_heading: "முடிவுகள்",
    highlighted_label: "குறிக்கப்பட்ட உரை",
    corrected_label: "திருத்தப்பட்ட உரை (திருத்தலாம்)",
    corrected_placeholder: "திருத்தப்பட்ட உரை இங்கே தோன்றும்…",
    results_placeholder: "முடிவுகள் இங்கே தோன்றும்…",
    copy_btn: "📋 நகலெடு",
    save_btn: "✍️ என் திருத்தங்களைச் சேமி",
    errorlist_heading: "பிழை பட்டியல்",
    errors_placeholder: "உரையை உள்ளிட்டு சரிபார் என்பதை அழுத்தவும்.",
    loading_msg: "Gemini மூலம் சரிபார்க்கிறது...",

    counter: "%s சொற்கள் · %s எழுத்துகள்",

    lang_si: "சிங்களம்", lang_ta: "தமிழ்", lang_en: "ஆங்கிலம்",
    type_spelling: "எழுத்துப்பிழை", type_grammar: "இலக்கணம்",
    type_grammar_discord: "இலக்கணம்", type_punctuation: "நிறுத்தற்குறி",
    type_encoding_error: "encoding",

    enter_text: "தயவுசெய்து உரையை உள்ளிடவும்",
    conn_error: "இணைப்பு பிழை",
    copied: "நகலெடுக்கப்பட்டது 📋",
    nothing_copy: "நகலெடுக்க எதுவும் இல்லை",
    no_changes: "மாற்றங்கள் இல்லை",
    saved_n: "%s திருத்தம்(ங்கள்) சேமிக்கப்பட்டன",
    no_errors: "பிழைகள் இல்லை ✅",
    errors_found: "%s பிழை(கள்) கண்டறியப்பட்டன",
    rate_limited: "வேண்டுகோள் வரம்பு மீறப்பட்டது — ஒரு நிமிடத்தில் மீண்டும் முயற்சிக்கவும்.",
    save_nothing: "சேமிக்க எதுவும் இல்லை",
    check_first: "முதலில் உரையைச் சரிபார்க்கவும்",
    confirm_save: "இந்த %s திருத்தத்தைச் சேமிக்கவா?",
    save_failed: "சேமிப்பு தோல்வியடைந்தது",

    login_title: "உள்நுழைக",
    login_sub: "சிங்களம் · தமிழ் · ஆங்கிலம் சரிபார்ப்பான்",
    username_label: "பயனர் பெயர்",
    password_label: "கடவுச்சொல்",
    login_btn: "உள்நுழைக →",
  },
};

(function () {
  const LANG_KEY = "sp-lang";
  const SUPPORTED = ["en", "si", "ta"];

  function initialLang() {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
    const srv = (window.__UI_LANG__ || "").slice(0, 2);
    if (SUPPORTED.includes(srv)) return srv;
    const nav = (navigator.language || "en").slice(0, 2);
    return SUPPORTED.includes(nav) ? nav : "en";
  }

  let current = initialLang();
  window.currentLang = () => current;

  window.t = function (key) {
    const args = Array.prototype.slice.call(arguments, 1);
    const dict = window.I18N[current] || window.I18N.en;
    let s = (dict[key] != null) ? dict[key]
          : (window.I18N.en[key] != null ? window.I18N.en[key] : key);
    if (args.length) { let i = 0; s = s.replace(/%[sd]/g, () => args[i++]); }
    return s;
  };

  window.applyLanguage = function (lang) {
    if (!SUPPORTED.includes(lang)) return;
    current = lang;
    localStorage.setItem(LANG_KEY, lang);
    document.documentElement.setAttribute("lang", lang);
    document.documentElement.setAttribute("data-lang", lang);

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = window.t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
      el.setAttribute("placeholder", window.t(el.getAttribute("data-i18n-ph")));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.setAttribute("title", window.t(el.getAttribute("data-i18n-title")));
    });
    document.querySelectorAll("[data-lang-btn]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-lang-btn") === lang);
    });
    document.dispatchEvent(new CustomEvent("langchange", { detail: { lang } }));
  };

  // Switcher (event delegation).
  document.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("[data-lang-btn]");
    if (btn) window.applyLanguage(btn.getAttribute("data-lang-btn"));
  });

  document.addEventListener("DOMContentLoaded", () => window.applyLanguage(current));
})();
