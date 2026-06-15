# Gemini API Usage for Sinhala Proofreading

Two call paths in this project:
- **Client Direct mode** → `engine/gemini_engine.py` uses `google-generativeai`
  (REST transport).
- **Control PC proxy** → `proxy_server/gemini_rest.py` uses **plain HTTPS REST via
  `requests`** (no SDK — avoids the deprecated package that 404s on Python 3.14).

## Models
- Default: **`gemini-2.5-flash`** (good Sinhala, generous free quota).
- `gemini-flash-latest` (always-newest flash) is a fine alternative.
- **`gemini-2.0-flash` is retired** for new keys → 404 "no longer available".
- Avoid `*-pro` for many shared users — its free-tier rate limit is low.
- The admin panel lists the key's real models (`GET /v1beta/models`) and the proxy
  **auto-switches** off an unavailable model to a working `flash` one.

## REST call (what the proxy does)
```python
import requests
ROOT = "https://generativelanguage.googleapis.com/v1beta"

def generate(api_key, model, prompt):
    url = f"{ROOT}/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.05,
                             "responseMimeType": "application/json"},  # force JSON
    }
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    cand = r.json()["candidates"][0]
    return "".join(p.get("text", "") for p in cand["content"]["parts"])

def list_models(api_key):
    r = requests.get(f"{ROOT}/models?key={api_key}&pageSize=200", timeout=15)
    r.raise_for_status()
    return [m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]
```

## SDK call (what Direct mode does)
```python
import google.generativeai as genai
genai.configure(api_key=api_key, transport="rest")     # plain HTTPS, firewall-friendly
model = genai.GenerativeModel("gemini-2.5-flash")
cfg = genai.types.GenerationConfig(temperature=0.05, response_mime_type="application/json")
resp = model.generate_content(prompt, generation_config=cfg)
data = json.loads(resp.text)
```

## Error handling (map HTTP/status → friendly bilingual message)
| Signal | Meaning | Action |
|---|---|---|
| 404 "not found / no longer available" | model retired/unavailable for key | pick another model (dropdown) |
| 400 / "API key not valid" | bad key | re-enter the key |
| 401 / 403 | invalid key / no access | check key + project |
| 429 / "quota" / "resource_exhausted" | rate/quota limit | use a flash model, wait, or enable billing |
| network / SSL / DNS | offline / blocked | check internet + firewall (allow `:443`) |

Always surface the API's own `error.message` on 404/400 — it states the exact cause.

## Robust JSON parsing
Model output may be wrapped in ```` ```json ```` fences. Strip fences, then
`json.loads`; on failure, regex-extract the first `{...}` block; on total failure
return a safe empty result (never crash).

## Reliability rules
- Confidence threshold ≥ 0.75 (≥ 0.85 colloquial); max 10 errors per response.
- Inject top human-verified corrections as few-shot examples; list present English
  words so they're never flagged.
- API key stored outside the app: `~/.sinhala_proofreader/config.json` (Direct) or
  `proxy_server/api_key.txt` (Control PC — git-ignored).
