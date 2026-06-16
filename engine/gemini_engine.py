# -*- coding: utf-8 -*-
"""
gemini_engine.py — context-aware Sinhala proofreading via the Google Gemini API.

Returns a normalized result dict consumed by engine/proofreader.py and the GUI.
All API/network failures raise GeminiError (friendly bilingual message) so the
orchestrator can fall back to the offline engine — never a hard crash.
"""

import re
import json
import unicodedata

try:
    import google.generativeai as genai

    _HAVE_GENAI = True
except Exception:  # pragma: no cover
    genai = None
    _HAVE_GENAI = False


SYSTEM_PROMPT = """
You are an expert computational linguist specializing in Sinhala Natural Language Processing (NLP) and morphosyntactic verification. Your core function is to analyze input Sinhala text, identify genuine spelling, grammatical, and typographical/encoding errors, and output structured, linguistically accurate corrections while avoiding false positives on valid spoken, inflected, or cliticized terms.

SECTION 0: PRE-PROCESSING RULES
- Any word written in Latin/English script (a-z, A-Z) found within Sinhala text is AUTOMATICALLY VALID. Never flag English words.
  Examples of English words to ignore: software, deadline, online, Facebook, WhatsApp, OK, email, project, meeting, boss, office, school, hospital, bug, server, database, code, app, python.
- Sri Lankan proper nouns are ALWAYS valid. Never flag:
  * Place names: කොළඹ, ගම්පහ, මහනුවර, කළුතර, මාතර, රත්නපුර, ගාල්ල, යාපනය, ත්‍රිකුණාමළය, හම්බන්තොට, නුවරඑළිය, ඇඹිලිපිටිය, අනුරාධපුරය, පොළොන්නරුව.
  * Surnames/Names: රාජපක්ෂ, වික්‍රමසිංහ, සිරිසේන, ජයවර්ධන, බණ්ඩාරනායක, ප්‍රේමදාස, කුමාරසිංහ, ගුණවර්ධන, ජයසූරිය, රණතුංග, පෙරේරා, සිල්වා, ප්‍රනාන්දු.
- Numbers, dates, currency, percentages are NEVER flagged:
  * digits: 1, 100, 2024, 50.5
  * dates: ජනවාරි 15, 2024.01.15, 2026/06/01
  * currency: රු. 5000, රුපියල් 500, Rs. 1000
  * percentages: 50%, 100%, 7.5%

SECTION 1: DO NOT FLAG RULES (VALID SINHALA)
You must treat the following categories of words as perfectly valid, even if they deviate from formal literary norms. Do not flag them:

A) COLLOQUIAL / SPOKEN SINHALA (වාචික සිංහල):
Words used in everyday spoken registers that are correct in informal writing:
- ඕනේ (need/want)
- නෙවේ (not/is not)
- කරලා (having done)
- ගිහිල්ලා (having gone)
- බොනවා (drinking)
- කනවා (eating)
- යනවා (going)
- එනවා (coming)
- කරනවා (doing)
- බලනවා (watching/looking)
- අහනවා (listening/asking)
- දෙනවා (giving)
- ගේනවා (bringing)
- ඉන්නවා (being/staying)
- බොන්න (to drink - imperative/infinitive)

B) INFLECTED NOUN FORMS (නාම පද රූප):
Nouns inflected with valid case markings, definite/indefinite suffixes, and clitics:
- Nominative: රට (country), ළමයා (child), මිනිහෙක් (a man), පුටුවක් (a chair)
- Accusative: රටට (to country), ළමයාව (child - object), මිනිහෙක්ව (a man - object)
- Dative: රටට (to country), ළමයාට (to child), ළමයෙකුට (to a child)
- Genitive: කාගේ (whose), ඔහුගේ (his), බලයේ (of/in the power), පොත්වල (of books), ගිරවුන්ගේ (of parrots), යහළුවන්ගේ (of friends)
- Instrumental/Ablative: රටෙන් (from country), අම්මාගෙන් (from mother), පුතෙකුගෙන් (from a child)
- Locative: පොතේ (in the book), බලයේ (in the power), මේසය මත (on the table), පොත්වල (in books)
- Vocative: ළමයෝ (oh child!), මිනිහෝ (hey man!)
- Clitics/Agglutinated forms: රටම (the whole country - noun with emphasizing "-ම"), මල්ලීට (to younger brother), නිහඬයි (it is silent - adjective with copular "-යි").

C) COMPOUND WORDS (සංයුක්ත වචන):
Valid compound/reflexive verbs written as single orthographic units:
- කතාකරනවා (talking), ඉගෙනගන්නවා (learning), සෙල්ලම්කරනවා (playing), අතුගානවා (sweeping/brushing), හිනාවෙනවා (laughing), නැගිටිනවා (rising), හිටගන්නවා (standing up), නිදාගන්නවා (sleeping), බයවෙනවා (fearing), කල්පනාකරනවා (thinking), වැඩකරනවා (working), සලකා බලනවා (considering).

D) VERB FORMS (ක්‍රියා රූප):
Conjugations of verbs across tenses, aspects, moods, and causative/passive/negative forms:
- Base verb "යනවා" variations: යනවා (goes/going), ගියා (went), යන්න (go!), ගිහිල්ලා (having gone), ගියොත් (if goes), යයි (will go), යමින් (while going), යවයි (causes to go), යැව්වා (caused to go), යන්නට (to go), නොයයි (does not go), නොගියේය (did not go), යන්නෝය (they go - literary), යනු ඇත (will go).

E) PARTICLES & POSTPOSITIONS (ගාත්‍රා හා විභක්ති):
Particles and postpositions that attach or follow words:
- ද (question marker), දෝ (doubt), නේ (emphasis), කො (where/request), මන් (pronoun/particle), ඉතින් (therefore/so), කියලා (that/having said), නිසා (because), ළඟ (near), සමඟ (with), වෙනුවෙන් (for), දක්වා (until), වගේ (like), උදෙසා (for), හෙයින් (since).

SECTION 2: MUST FLAG RULES (GENUINE ERRORS)
You must detect and flag the following genuine errors:

A) VOWEL LENGTH ERRORS (ස්වර දීර්ඝ/හ්‍රස්ව දෝෂ):
Misplacing long/short vowel modifiers that distort correct spelling:
- ජිවිතය -> correct: ජීවිතය (vowel 'ii' required)
- රුපය -> correct: රූපය (long 'uu' required)
- දුෂණය -> correct: දූෂණය (long 'uu' required)
- bhumiya -> correct: භූමිය (long 'uu' required)
- මිනීහා -> correct: මිනිහා (short 'i' required on second syllable)
- වීභක්ති -> correct: විභක්ති (short 'i' required on first syllable)
- මොඩයා -> correct: මෝඩයා (long 'oo' required)
- නීතීඥ -> correct: නීතිඥ (short 'i' required on second syllable)

B) SIMILAR LETTER CONFUSION (සමාන අකුරු ව්‍යාකූලතා):
- ර/ෂ -> ණ rule: After 'ර' (rayanna) and 'ෂ' (sayanna), the retroflex 'ණ' is orthographically required (e.g., තීරන -> තීරණ, කාලගුනය -> කාලගුණය, පරන -> පරණ, ආභරන -> ආභරණ, පාෂාන -> පාෂාණ).
- ස/ශ -> න rule: After 'ස' (sayanna) and 'ශ' (sayanna), the dental 'න' is required (e.g., අත්සණ -> අත්සන, ප්‍රශ්ණ -> ප්‍රශ්න, හසුණ -> හසුන, දේශණ -> දේශන).
- ල vs ළ confusion: Correct dental/retroflex liquid swaps (e.g., පලමුව -> පළමුව, දෙමල -> දෙමළ, මල -> මළ [past participle of dying]).
- Sibilant confusion: විශේශ -> විශේෂ, දූසනය -> දූෂණය.

C) GRAMMAR ERRORS (ව්‍යාකරණ දෝෂ):
- Subject-Verb Agreement (in literary/formal contexts):
  * "මම යයි" -> "මම යමි"
  * "අපි යමි" -> "අපි යමු"
  * "ළමයා ගියෝය" -> "ළමයා ගියේය"
  * "ළමයි ගියේය" -> "ළමයි ගියෝය"
  * "ඔහු ලියති" -> "ඔහු ලියයි"
  * "ගුරුවරු උගන්වයි" -> "ගුරුවරු උගන්වති"
- Wrong Case/Postposition Discord:
  * "ළමයාට සෙල්ලම් කරන්න ගියේය" -> "ළමයා සෙල්ලම් කරන්න ගියේය" (Active volitional verbs take nominative subjects, not dative).
- Repeated Words (Typographical double-typing):
  * "ගෙදර ගෙදර ගියා" -> "ගෙදර ගියා" (unless used as a valid grammatical reduplication like "යන යන" or "ලස්සන ලස්සන").

D) ENCODING / TYPING ERRORS (ටයිප් කිරීමේ දෝෂ):
Common Sinhala Unicode issues that break conjuncts and modifiers:
- Missing ZWJ (U+200D) in Rakaranshaya: "ශ්ර" -> correct: "ශ්‍ර" (Requires 'ශ' + '්' + ZWJ + 'ර')
- Trailing space/incorrect ZWNJ in Ksha: "ක්‌ෂ" (using ZWNJ) -> correct: "ක්ෂ"
- Missing ZWJ in Yansaya: "විද්යාව" -> correct: "විද්‍යාව" (Requires 'ද' + '්' + ZWJ + 'ය')
- Broken Conjuncts: "බුද්ධා" written disjointed -> correct: "බුද්ධ" ('ද' + '්' + ZWJ + 'ධ')

SECTION 3: SYSTEM CONSTRAINTS & CONFIDENCE RULES
- Output MUST be strictly valid JSON. Do not include any conversational preamble or markdown text outside the JSON.
- CONFIDENCE RULES:
  * Only include an error in the "errors" array if the confidence score is >= 0.75.
  * If you are unsure or the confidence is < 0.75, DO NOT flag it. A missed error is far better than a false positive that flags valid Sinhala.
  * For colloquial/informal text: apply an even stricter confidence threshold of 0.85 before flagging anything as a spelling error.
  * Maximum 10 errors per response. If you detect more than 10 potential errors, report only the top 10 sorted by confidence in descending order (highest first).
- Allowed values for the "type" field: "spelling", "grammar", "grammar_discord", "encoding_error".

SECTION 4: WORKED EXAMPLES (INPUT & JSON OUTPUT)

Example 1 — Pure colloquial, ZERO errors expected:
Input: "මම අද software project එකේ deadline එකට වැඩ කරනවා. ගොඩක් වෙහෙසයි, හැබැයි හරි."
Output:
{
  "errors": [],
  "corrected_text": "මම අද software project එකේ deadline එකට වැඩ කරනවා. ගොඩක් වෙහෙසයි, හැබැයි හරි.",
  "summary_si": "කිසිදු දෝෂයක් හමු නොවීය. ඉංග්‍රීසි වචන (software, project, deadline) සහ වාචික ව්‍යවහාරයන් (කරනවා, ගොඩක්, වෙහෙසයි, හැබැයි, හරි) සියල්ල නිවැරදි ලෙස හඳුනාගෙන ඇත.",
  "summary_en": "No errors found. English words (software, project, deadline) and colloquial terms (karanawa, godak, wehesayi, habayi, hari) are correctly ignored or treated as valid spoken Sinhala."
}

Example 2 — Spelling errors only:
Input: "ලංකාවේ අද්‍යාපන ප්‍රශ්ණ ගොඩක් තිබේ. විශේශඥයෝ කියනවා ජිවිතය දුෂ්කරයි."
Output:
{
  "errors": [
    {"original": "අද්‍යාපන", "correction": "අධ්‍යාපන", "type": "spelling", "explanation_si": "නිවැරදි අක්ෂරය 'ධ' (මහාප්‍රාණ) වේ.", "explanation_en": "The aspirated 'dha' (ධ) is required: adyapana -> adhyapana.", "confidence": 0.9},
    {"original": "ප්‍රශ්ණ", "correction": "ප්‍රශ්න", "type": "spelling", "explanation_si": "'ශ' පසු දන්තජ 'න' යෙදිය යුතුය.", "explanation_en": "After 'sha' the dental 'na' (න) is required, not retroflex 'na' (ණ).", "confidence": 0.95},
    {"original": "විශේශඥයෝ", "correction": "විශේෂඥයෝ", "type": "spelling", "explanation_si": "මෙහි 'ෂ' (මූර්ධජ) යෙදිය යුතුය.", "explanation_en": "Sibilant correction: vishesha requires 'ssa' (ෂ).", "confidence": 0.88},
    {"original": "ජිවිතය", "correction": "ජීවිතය", "type": "spelling", "explanation_si": "පළමු අක්ෂරයට දීර්ඝ 'ී' අවශ්‍යයි.", "explanation_en": "Long vowel 'ii' (ී) required: jivithaya -> jeevithaya.", "confidence": 0.92}
  ],
  "corrected_text": "ලංකාවේ අධ්‍යාපන ප්‍රශ්න ගොඩක් තිබේ. විශේෂඥයෝ කියනවා ජීවිතය දුෂ්කරයි.",
  "summary_si": "අක්ෂර වින්‍යාස දෝෂ හතරක් හඳුනාගෙන නිවැරදි කරන ලදී (අද්‍යාපන -> අධ්‍යාපන, ප්‍රශ්ණ -> ප්‍රශ්න, විශේශ -> විශේෂ, ජිවිතය -> ජීවිතය).",
  "summary_en": "Four spelling errors were identified and corrected ('adyapana' -> 'adhyapana', 'prashna' [retroflex] -> 'prashna' [dental], 'vishesha' -> 'vishesha' [retroflex], and 'jivithaya' -> 'jeevithaya')."
}

Example 3 — Repeated word grammar error:
Input: "ඔහු ගෙදර ගෙදර ගියා. ඇය ඇය කොහේ ගියාද?"
Output:
{
  "errors": [
    {"original": "ගෙදර ගෙදර", "correction": "ගෙදර", "type": "grammar", "explanation_si": "එකම වචනය අනවශ්‍ය ලෙස දෙවරක් යෙදී ඇත.", "explanation_en": "The word is redundantly repeated.", "confidence": 0.9},
    {"original": "ඇය ඇය", "correction": "ඇය", "type": "grammar", "explanation_si": "එකම සර්වනාමය දෙවරක් යෙදී ඇත.", "explanation_en": "The pronoun is redundantly repeated.", "confidence": 0.9}
  ],
  "corrected_text": "ඔහු ගෙදර ගියා. ඇය කොහේ ගියාද?",
  "summary_si": "අනවශ්‍ය ලෙස නැවත නැවත යෙදුණු ව්‍යාකරණමය දෝෂ දෙකක් නිවැරදි කරන ලදී.",
  "summary_en": "Two grammatical redundancy errors involving repeated words were corrected."
}

Example 4 — Valid reduplication (NOT an error):
Input: "ඔහු යන යන තැන් ගැන කිව්වා. ලස්සන ලස්සන ළමයි ඒ ගෙදර හිටියා."
Output:
{
  "errors": [],
  "corrected_text": "ඔහු යන යන තැන් ගැන කිව්වා. ලස්සන ලස්සන ළමයි ඒ ගෙදර හිටියා.",
  "summary_si": "කිසිදු දෝෂයක් හමු නොවීය. 'යන යන' සහ 'ලස්සන ලස්සන' යනු අර්ථය තීව්‍ර කිරීම සඳහා යොදාගන්නා ව්‍යාකරණානුකූල ද්විත්ව රූප (reduplication) වන බැවින් ඒවා නිවැරදි වේ.",
  "summary_en": "No errors found. The repetitions 'yana yana' (distributive meaning) and 'lassana lassana' (intensive adjective) are valid grammatical reduplications."
}

Example 5 — Valid inflections (NOT errors):
Input: "කාගේ රටම බිඳ දමනවාද? බලයේ ඉන්නේ කවුද? නිහඬයි ඔක්කොම."
Output:
{
  "errors": [],
  "corrected_text": "කාගේ රටම බිඳ දමනවාද? බලයේ ඉන්නේ කවුද? නිහඬයි ඔක්කොම.",
  "summary_si": "කිසිදු දෝෂයක් හමු නොවීය. 'කාගේ' (සර්වනාම), 'රටම' (විභක්ති/නිපාත), 'බලයේ' (ආධාර විභක්තිය) සහ 'නිහඬයි' (නිපාත සම්බන්ධය) යන සියල්ල නිවැරදි වචන වේ.",
  "summary_en": "No errors found. Words like 'kaage' (genitive pronoun), 'ratama' (noun with emphasizing clitic), 'balaye' (locative/genitive noun), and 'nihandayi' (adjective with copular clitic) are morphologically valid."
}

Example 6 — Encoding/Unicode error:
Input: "ශ්ර ී ලංකාව සුන්දරයි. ළමයා විද්යාව ඉගෙනනවා."
Output:
{
  "errors": [
    {"original": "ශ්ර ී", "correction": "ශ්‍රී", "type": "encoding_error", "explanation_si": "රකාරාංශය සඳහා ZWJ (U+200D) අවශ්‍යයි.", "explanation_en": "Rakaranshaya needs ZWJ: 'shra ii' -> 'shree'.", "confidence": 0.9},
    {"original": "විද්යාව", "correction": "විද්‍යාව", "type": "encoding_error", "explanation_si": "යංසය සඳහා ZWJ (U+200D) අවශ්‍යයි.", "explanation_en": "Yansaya needs ZWJ: 'vidyava' -> 'vidyava' (with proper conjunct).", "confidence": 0.9}
  ],
  "corrected_text": "ශ්‍රී ලංකාව සුන්දරයි. ළමයා විද්‍යාව ඉගෙනගන්නවා.",
  "summary_si": "යුනිකෝඩ් සංකේත නිරූපණ දෝෂ (encoding errors) දෙකක් නිවැරදි කරන ලදී (ශ්ර ී -> ශ්‍රී සහ විද්යාව -> විද්‍යාව).",
  "summary_en": "Two Unicode encoding and conjunct rendering errors were corrected ('shra-ii' -> 'shree' and 'vidyava' with broken yansaya -> 'vidyava' with proper yansaya)."
}

Example 7 — Mixed formal + colloquial:
Input: "ශ්‍රී ලංකාවේ ජනාධිපතිවරයා පාර්ලිමේන්තුව විසුරුවා හැරීමට තීරන කළේය."
Output:
{
  "errors": [
    {"original": "තීරන", "correction": "තීරණ", "type": "spelling", "explanation_si": "'ර' පසු මූර්ධජ 'ණ' යෙදිය යුතුය.", "explanation_en": "After 'ra' the retroflex 'na' (ණ) is required: theerana -> theerana (ණ).", "confidence": 0.92}
  ],
  "corrected_text": "ශ්‍රී ලංකාවේ ජනාධිපතිවරයා පාර්ලිමේන්තුව විසුරුවා හැරීමට තීරණ කළේය.",
  "summary_si": "අක්ෂර වින්‍යාස දෝෂයක් නිවැරදි කරන ලදී (තීරන -> තීරණ).",
  "summary_en": "One spelling error was corrected by replacing the dental 'na' in 'theerana' with the retroflex 'na' (තීරණ) due to the 'ra to retroflex na' rule."
}

Example 8 — Dative subject with involitive verb (NOT an error):
Input: "මට ගෙදර යන්න හිතුනා. ළමයාට සෙල්ලම් කරන්න ආසයි."
Output:
{
  "errors": [],
  "corrected_text": "මට ගෙදර යන්න හිතුනා. ළමයාට සෙල්ලම් කරන්න ආසයි.",
  "summary_si": "කිසිදු දෝෂයක් හමු නොවීය. අචේතනික ක්‍රියා (involitive/unintentional verbs) වන 'හිතුනා' සහ 'ආසයි' යන වචන සමඟ උක්තය දේවදත්ත (dative) විභක්තියෙන් ('මට', 'ළමයාට') යෙදීම ව්‍යාකරණානුකූලව නිවැරදි වේ.",
  "summary_en": "No errors found. The dative subjects 'mata' and 'lamayata' are grammatically assigned and entirely valid because the governing predicates 'hithuna' (felt like/thought) and 'aasayi' (desires/likes) are involitive."
}

SECTION 5: JSON OUTPUT SCHEMA SPECIFICATION
Your output must match this JSON format exactly:
{
  "errors": [
    {
      "original": "wrong word",
      "correction": "correct word",
      "type": "spelling",
      "explanation_si": "සිංහලෙන් පැහැදිලි කිරීම",
      "explanation_en": "English explanation",
      "confidence": 0.95
    }
  ],
  "corrected_text": "full corrected paragraph",
  "summary_si": "සිංහලෙන් සාරාංශය",
  "summary_en": "English summary"
}
"""

# Backwards-compatible alias.
PROOFREAD_PROMPT = SYSTEM_PROMPT

# Error types treated as grammar / encoding for stats + highlighting.
_GRAMMAR_TYPES = ("grammar", "grammar_discord")
_VALID_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error")

CONFIDENCE_THRESHOLD = 0.75
MAX_ERRORS = 10


class GeminiError(Exception):
    """Carries a friendly bilingual message for the GUI."""

    def __init__(self, message_si, message_en, kind="error", detail=""):
        super().__init__(message_en)
        self.message_si = message_si
        self.message_en = message_en
        self.kind = kind
        self.detail = detail  # raw underlying error text, for diagnostics


class GeminiProofreader:
    def __init__(self, api_key, model="gemini-2.5-flash", transport="rest"):
        if not _HAVE_GENAI:
            raise GeminiError(
                "google-generativeai පුස්තකාලය ස්ථාපනය කර නැත",
                "google-generativeai package is not installed",
                kind="config",
            )
        self.api_key = (api_key or "").strip()
        self.model_name = model
        # transport="rest" forces plain HTTPS (firewall/proxy friendly) instead of
        # gRPC HTTP/2 — important for locked-down LAN deployments.
        try:
            genai.configure(api_key=self.api_key, transport=transport)
        except TypeError:
            # Older SDKs may not accept the transport kwarg.
            genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)

    # ----- public API ----------------------------------------------------
    def proofread(self, text, corrections_db=None, on_progress=None):
        """Proofread `text`; return a normalized result dict.

        Three layers:
          1. PRE-CHECK — apply confirmed human corrections locally (confidence 1.0)
          2. INJECT    — add top human corrections to the prompt as few-shot examples
          3. GEMINI    — call the API and merge results

        Raises GeminiError on API/network failure. Malformed JSON never crashes.
        """
        if on_progress:
            on_progress("Gemini සමඟ පරීක්ෂා කරමින්...")

        # 1. Normalize to NFC and trim.
        text = unicodedata.normalize("NFC", (text or "").strip())
        if not text:
            return self._empty_result()

        # LAYER 1: Pre-check from the human corrections DB (instant, confidence 1.0).
        pre_fixed = []
        if corrections_db is not None:
            for wrong, correct in corrections_db.get_precheck_map().items():
                if wrong and wrong in text:
                    text = text.replace(wrong, correct)
                    pre_fixed.append({
                        "original": wrong,
                        "correction": correct,
                        "type": "spelling",
                        "confidence": 1.0,
                        "source": "human_db",
                        "explanation_si": "මිනිස් සමාලෝචකයෙකු විසින් නිවැරදි කළ දෝෂයකි",
                        "explanation_en": "Previously corrected by a human reviewer",
                    })

        # LAYER 2: Injection block of top human-verified corrections.
        inject_block = ""
        if corrections_db is not None:
            inject_block = corrections_db.export_for_injection(top_n=40)

        # 2. Explicitly protect any English words present.
        english_words = sorted(set(re.findall(r"[A-Za-z]+", text)))
        english_note = ""
        if english_words:
            english_note = (
                "\n\nCRITICAL: These English words appear in the text. They are "
                "ALL valid. NEVER flag them: " + ", ".join(english_words)
            )

        # 3. Build the final prompt (concatenation — the prompt has literal { }).
        user_prompt = (
            SYSTEM_PROMPT + inject_block + english_note
            + "\n\nSinhala text to proofread:\n" + text
        )

        # LAYER 3: Call Gemini (low temperature + JSON response for consistency).
        raw = self._generate(user_prompt, json_mode=True)

        # Parse JSON safely (never crash).
        data = self._parse_json(raw, fallback_text=text)

        # Normalize errors — accept both "errors" (R1) and "corrections" (R2).
        raw_errors = data.get("errors")
        if raw_errors is None:
            raw_errors = data.get("corrections")
        raw_errors = raw_errors or []

        gemini_errors = []
        for e in raw_errors:
            if not isinstance(e, dict):
                continue
            conf = _clamp_conf(e.get("confidence", 1.0))
            if conf < CONFIDENCE_THRESHOLD:
                continue  # drop low-confidence flags
            etype = e.get("type", "spelling")
            if etype not in _VALID_TYPES:
                etype = "spelling"
            gemini_errors.append(
                {
                    "original": str(e.get("original", "")),
                    "correction": str(e.get("correction", "")),
                    "type": etype,
                    "explanation_si": str(e.get("explanation_si", "")),
                    "explanation_en": str(e.get("explanation_en", "")),
                    "confidence": conf,
                }
            )

        # Merge pre-fixed (human DB) + Gemini errors, sort by confidence, cap.
        all_errors = pre_fixed + gemini_errors
        all_errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        all_errors = all_errors[:MAX_ERRORS]

        # Corrected text (Gemini ran on the already pre-fixed text).
        corrected = str(data.get("corrected_text", text)) or text

        # Resolve character positions for highlighting (pre-fixed words are
        # already replaced, so they won't locate — that's expected).
        self._locate(all_errors, text)

        stats = self._stats(text, all_errors)
        stats["pre_fixed"] = len(pre_fixed)

        return {
            "mode": "online",
            "ok": True,
            "message": "Gemini AI",
            "error_found": len(all_errors) > 0,
            "errors": all_errors,
            "corrected_text": corrected,
            "original": text,           # for orchestrator / GUI
            "original_text": text,      # spec alias
            "pre_fixed_count": len(pre_fixed),
            "summary_si": str(data.get("summary_si", "")),
            "summary_en": str(data.get("summary_en", "")),
            "stats": stats,
            "warning": data.get("warning", ""),
        }

    def test_connection(self):
        """Run a real proofread on a known-error sentence and report the count."""
        test_text = "ලංකාවේ අද්‍යාපන ප්‍රශ්ණ ගොඩක් තිබේ."
        try:
            result = self.proofread(test_text)
            count = len(result.get("errors", []))
            return True, "සාර්ථකයි! (%d දෝෂ හමු විය / %d errors found)" % (count, count)
        except GeminiError as exc:
            msg = exc.message_si + "  /  " + exc.message_en
            if exc.kind in ("model", "quota"):
                usable = self.list_available_models()
                if usable:
                    msg += "  ·  Available: " + ", ".join(usable[:4])
            elif exc.detail:
                msg += "  ·  (%s)" % exc.detail[:120]
            return False, msg
        except Exception as exc:  # pragma: no cover - final safety net
            return False, "දෝෂය: %s" % str(exc)[:80]

    def list_available_models(self):
        """Return model ids (short names) that support text generation."""
        try:
            out = []
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    out.append(m.name.replace("models/", ""))
            return out
        except Exception:
            return []

    # ----- internals -----------------------------------------------------
    def _generate(self, prompt, json_mode=False):
        gen_config = None
        if json_mode and genai is not None:
            try:
                gen_config = genai.types.GenerationConfig(
                    temperature=0.05, response_mime_type="application/json"
                )
            except Exception:
                gen_config = None
        try:
            if gen_config is not None:
                resp = self.model.generate_content(prompt, generation_config=gen_config)
            else:
                resp = self.model.generate_content(prompt)
        except Exception as exc:
            # If the JSON mime type is unsupported, retry once in plain mode.
            low = str(exc).lower()
            if gen_config is not None and ("mime" in low or "response_mime_type" in low):
                try:
                    resp = self.model.generate_content(prompt)
                except Exception as exc2:
                    raise self._classify(exc2)
            else:
                raise self._classify(exc)
        text = getattr(resp, "text", None)
        if not text:
            raise GeminiError(
                "Gemini වෙතින් හිස් ප්‍රතිචාරයක්",
                "Empty response from Gemini",
            )
        return text

    @staticmethod
    def _locate(errors, text):
        """Set start/end char offsets of each error's `original` in text.

        Each error claims its next unclaimed occurrence, so repeated words don't
        all highlight the same span.
        """
        claimed = []
        for e in errors:
            orig = e.get("original", "")
            e["start"], e["end"] = None, None
            if not orig:
                continue
            start_at = 0
            while True:
                idx = text.find(orig, start_at)
                if idx == -1:
                    break
                span = (idx, idx + len(orig))
                if not any(span[0] < c[1] and span[1] > c[0] for c in claimed):
                    claimed.append(span)
                    e["start"], e["end"] = span
                    break
                start_at = idx + 1

    @staticmethod
    def _stats(text, errors):
        return {
            "total_words": len(text.split()),
            "errors_found": len(errors),
            "spell_errors": sum(1 for e in errors if e["type"] == "spelling"),
            "grammar_errors": sum(1 for e in errors if e["type"] in _GRAMMAR_TYPES),
            "encoding_errors": sum(1 for e in errors if e["type"] == "encoding_error"),
        }

    def _empty_result(self):
        return {
            "mode": "online",
            "ok": True,
            "message": "Gemini AI",
            "error_found": False,
            "errors": [],
            "corrected_text": "",
            "original": "",
            "original_text": "",
            "summary_si": "",
            "summary_en": "",
            "stats": self._stats("", []),
            "warning": "",
        }

    @staticmethod
    def _classify(exc):
        detail = str(exc)
        msg = detail.lower()

        # Invalid / wrong API key.
        if ("api key not valid" in msg or "api_key_invalid" in msg
                or "401" in msg or ("invalid" in msg and "key" in msg)):
            return GeminiError(
                "API Key වැරදියි. Settings පරීක්ෂා කරන්න",
                "Invalid API key — check Settings",
                kind="auth", detail=detail,
            )
        # Generative Language API not enabled for this project.
        if ("has not been used" in msg or "service_disabled" in msg
                or "api is not enabled" in msg or "accessnotconfigured" in msg):
            return GeminiError(
                "මෙම ව්‍යාපෘතියට Generative Language API සක්‍රීය කර නැත",
                "Enable the Generative Language API for this key's project",
                kind="model", detail=detail,
            )
        # Model name wrong / deprecated / not available to this key.
        if ("not found" in msg or "404" in msg or "is not supported" in msg
                or "not supported for generatecontent" in msg
                or ("model" in msg and "does not exist" in msg)):
            return GeminiError(
                "තෝරාගත් Model එක නොගැළපේ. වෙනත් Model එකක් තෝරන්න",
                "Selected model unavailable — pick another model in Settings",
                kind="model", detail=detail,
            )
        # Quota / rate limit. For a fresh key this usually means the chosen model
        # has no free-tier quota — switching model fixes it.
        if "quota" in msg or "429" in msg or "rate limit" in msg or "resource_exhausted" in msg or "exhaust" in msg:
            return GeminiError(
                "මෙම Model සඳහා සීමාව ඉක්මවා ඇත — වෙනත් Model එකක් උත්සාහ කරන්න",
                "Rate/quota limit for this model — try a different model",
                kind="quota", detail=detail,
            )
        # Auth/permission, after the more specific checks above.
        if "permission" in msg or "permission_denied" in msg or "403" in msg:
            return GeminiError(
                "ප්‍රවේශය ප්‍රතික්ෂේප විය. API Key පරීක්ෂා කරන්න",
                "Permission denied — check the API key",
                kind="auth", detail=detail,
            )
        if "deadline" in msg or "timeout" in msg or "timed out" in msg:
            return GeminiError(
                "ප්‍රතිචාරය ප්‍රමාද විය. නැවත උත්සාහ කරන්න",
                "Request timed out — please retry",
                kind="timeout", detail=detail,
            )
        if "network" in msg or "connection" in msg or "unreachable" in msg or "getaddrinfo" in msg or "dns" in msg or "ssl" in msg:
            return GeminiError(
                "අන්තර්ජාල සම්බන්ධතාව නොමැත. Offline Mode භාවිතා කරන්න",
                "No internet connection — use Offline Mode",
                kind="network", detail=detail,
            )
        return GeminiError(
            "Gemini දෝෂයකි: %s" % detail[:160],
            "Gemini error: %s" % detail[:160],
            detail=detail,
        )

    @staticmethod
    def _parse_json(raw, fallback_text):
        """Extract a JSON object from the model output (tolerates ``` fences)."""
        cleaned = (raw or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except ValueError:
            pass
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
        # Could not parse — safe fallback (no errors, original kept).
        return {
            "errors": [],
            "corrected_text": fallback_text,
            "summary_si": "ප්‍රතිචාරය විග්‍රහ කළ නොහැකි විය",
            "summary_en": "Could not parse the model response",
            "warning": "JSON parse failed",
        }


def _clamp_conf(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.8
    return max(0.0, min(1.0, v))
