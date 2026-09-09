/* AI Proofreader Web App — main UI logic (vanilla JS). Multilingual (si/ta/en). */

(function () {
  "use strict";

  // ---------- theme ----------
  const THEME_KEY = "sp-theme";
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    const btn = document.getElementById("themeBtn");
    if (btn) btn.textContent = t === "dark" ? "☀️" : "🌙";
  }
  window.toggleTheme = function () {
    const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const next = cur === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  };
  applyTheme(localStorage.getItem(THEME_KEY) || "light");

  // ---------- elements ----------
  const $ = (id) => document.getElementById(id);
  const input = $("input");
  const counter = $("counter");
  const highlighted = $("highlighted");
  const corrected = $("corrected");
  const errorItems = $("errorItems");
  const summaryEl = $("summary");
  const chips = $("chips");
  const overlay = $("overlay");
  const detected = $("detected");
  const textLang = $("textLang");

  // Keep the last result so we can re-render labels when the UI language changes.
  let lastResult = null;
  let lastCorrectedText = "";

  // ---------- helpers ----------
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function toast(msg, kind) {
    const el = $("toast");
    el.textContent = msg;
    el.className = "toast show " + (kind || "");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.className = "toast"; }, 3000);
  }

  function updateCounter() {
    const text = input.value;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    counter.textContent = window.t("counter", words, text.length);
  }
  input.addEventListener("input", updateCounter);

  // ---------- highlight builder ----------
  const CLASS_FOR = {
    spelling: "spell-error",
    grammar: "grammar-error",
    grammar_discord: "grammar-error",
    punctuation: "grammar-error",
    encoding_error: "encoding-error",
  };

  function explOf(e) {
    return e.explanation_native || e.explanation_en || "";
  }

  function highlightErrors(text, errors) {
    const spans = errors
      .filter((e) => e.start != null && e.end != null)
      .map((e) => ({ start: e.start, end: e.end, e }))
      .sort((a, b) => a.start - b.start);
    let html = "";
    let cursor = 0;
    for (const s of spans) {
      if (s.start < cursor) continue;
      html += escapeHtml(text.slice(cursor, s.start));
      const cls = CLASS_FOR[s.e.type] || "spell-error";
      const tip = `${s.e.original} → ${s.e.correction}  ·  ${explOf(s.e)}`;
      html += `<mark class="${cls}" title="${escapeHtml(tip)}">${escapeHtml(text.slice(s.start, s.end))}</mark>`;
      cursor = s.end;
    }
    html += escapeHtml(text.slice(cursor));
    return html || "…";
  }

  const ICON_FOR = {
    spelling: "🔤", grammar: "📝", grammar_discord: "📝",
    punctuation: "❓", encoding_error: "🔧",
  };

  function renderErrorList(errors) {
    if (!errors.length) {
      errorItems.innerHTML = `<div class="empty-state">${escapeHtml(window.t("no_errors"))}</div>`;
      return;
    }
    errorItems.innerHTML = errors.map((e) => {
      const conf = Math.round((e.confidence || 0) * 100);
      const typeLabel = window.t("type_" + e.type);
      return `<div class="err ${e.type}">
        <div class="ico">${ICON_FOR[e.type] || "❗"}</div>
        <div class="body">
          <div class="change"><span class="from">${escapeHtml(e.original)}</span>
            &nbsp;→&nbsp;<span class="to">${escapeHtml(e.correction)}</span>
            <span class="tag">${escapeHtml(typeLabel)}</span></div>
          <div class="why">${escapeHtml(explOf(e))}</div>
        </div>
        <div class="conf">${conf}%</div>
      </div>`;
    }).join("");
  }

  function renderChips(stats, preFixed) {
    if (!stats) { chips.innerHTML = ""; return; }
    const chip = (label, n) => `<span class="chip">${escapeHtml(label)} <b>${n || 0}</b></span>`;
    const parts = [
      chip(window.t("type_spelling"), stats.spell_errors),
      chip(window.t("type_grammar"), stats.grammar_errors),
    ];
    if (preFixed) parts.unshift(`<span class="chip">✔ <b>${preFixed}</b></span>`);
    chips.innerHTML =
      `<span class="chip">Σ <b>${stats.errors_found || 0}</b></span>` + parts.join("");
  }

  function showDetected(lang) {
    if (!lang) { detected.hidden = true; return; }
    detected.hidden = false;
    detected.textContent = window.t("detected_as", window.t("lang_" + lang));
  }

  // Re-render dynamic content in the newly selected UI language.
  function rerender() {
    updateCounter();
    if (!lastResult) return;
    renderErrorList(lastResult.errors || []);
    renderChips(lastResult.stats, lastResult.pre_fixed_count);
    showDetected(lastResult.lang);
    const native = lastResult.summary_native || lastResult.summary_en || "";
    summaryEl.textContent = native;
  }
  document.addEventListener("langchange", rerender);

  // ---------- main actions ----------
  window.checkText = async function () {
    const text = input.value.trim();
    if (!text) { toast(window.t("enter_text"), "err"); input.focus(); return; }
    overlay.classList.add("show");
    try {
      const body = { text };
      const forced = textLang.value;
      if (forced) body.lang = forced;
      const res = await fetch("/api/proofread", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 401) { window.location = "/login"; return; }
      const data = await res.json();
      if (res.status === 429) { toast(window.t("rate_limited"), "err"); return; }
      if (!res.ok || data.ok === false) {
        toast(data.message_en || data.summary_en || window.t("conn_error"), "err");
        return;
      }

      lastResult = data;
      const original = data.original || text;
      highlighted.classList.remove("empty");
      highlighted.innerHTML = highlightErrors(original, data.errors || []);
      lastCorrectedText = data.corrected_text || original;
      corrected.value = lastCorrectedText;

      renderErrorList(data.errors || []);
      renderChips(data.stats, data.pre_fixed_count);
      showDetected(data.lang);
      summaryEl.textContent = data.summary_native || data.summary_en || "";

      const n = (data.errors || []).length;
      toast(n ? window.t("errors_found", n) : window.t("no_errors"), n ? "" : "ok");
    } catch (err) {
      toast(window.t("conn_error") + ": " + err.message, "err");
    } finally {
      overlay.classList.remove("show");
    }
  };

  window.clearText = function () {
    input.value = "";
    updateCounter();
    highlighted.innerHTML = window.t("results_placeholder");
    highlighted.classList.add("empty");
    corrected.value = "";
    lastCorrectedText = "";
    lastResult = null;
    errorItems.innerHTML = `<div class="empty-state">${escapeHtml(window.t("errors_placeholder"))}</div>`;
    chips.innerHTML = "";
    summaryEl.textContent = "";
    detected.hidden = true;
    input.focus();
  };

  window.copyCorrected = async function () {
    const text = corrected.value;
    if (!text) { toast(window.t("nothing_copy"), "err"); return; }
    try {
      await navigator.clipboard.writeText(text);
      toast(window.t("copied"), "ok");
    } catch {
      corrected.select();
      document.execCommand("copy");
      toast(window.t("copied"), "ok");
    }
  };

  window.saveCorrections = async function () {
    const edited = corrected.value.trim();
    if (!edited) { toast(window.t("save_nothing"), "err"); return; }
    if (!lastCorrectedText) { toast(window.t("check_first"), "err"); return; }

    const origWords = lastCorrectedText.trim().split(/\s+/);
    const newWords = edited.split(/\s+/);
    const corrections = [];
    const n = Math.min(origWords.length, newWords.length);
    for (let i = 0; i < n; i++) {
      if (origWords[i] !== newWords[i]) {
        corrections.push({ wrong: origWords[i], correct: newWords[i], type: "spelling" });
      }
    }
    if (!corrections.length) { toast(window.t("no_changes"), ""); return; }
    const preview = corrections.slice(0, 5).map((c) => `${c.wrong} → ${c.correct}`).join("\n");
    if (!confirm(window.t("confirm_save", corrections.length) + "\n\n" + preview +
        (corrections.length > 5 ? "\n…" : ""))) return;
    try {
      const lang = (lastResult && lastResult.lang) || "si";
      const res = await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections, lang }),
      });
      const data = await res.json();
      if (data.ok) { toast(window.t("saved_n", data.saved), "ok"); lastCorrectedText = edited; }
      else toast(window.t("save_failed"), "err");
    } catch (err) {
      toast(window.t("conn_error"), "err");
    }
  };

  // ================= voice typing (mic -> Gemini -> text) =================
  // Records with MediaRecorder, re-encodes to 16 kHz mono WAV (a format Gemini
  // accepts and that is small + ideal for speech), uploads to /api/transcribe,
  // then inserts the returned text at the caret in #input.
  const micBtn = $("micBtn");
  const micStatus = $("micStatus");
  const MAX_REC_MS = 60000;                 // hard cap: 60 s per take

  let mediaRecorder = null, mediaStream = null, chunks = [];
  let recTimer = null, recStart = 0, maxTimer = null, micState = "idle";

  function setMicState(state, msg) {
    micState = state;
    if (!micBtn) return;
    micBtn.classList.toggle("recording", state === "recording");
    micBtn.classList.toggle("busy", state === "busy");
    micBtn.disabled = (state === "busy");
    if (!micStatus) return;
    if (msg) { micStatus.hidden = false; micStatus.textContent = msg; }
    else { micStatus.hidden = true; micStatus.textContent = ""; }
    micStatus.classList.toggle("rec", state === "recording");
  }

  function fmtTime(ms) {
    const s = Math.floor(ms / 1000);
    return String(Math.floor(s / 60)) + ":" + String(s % 60).padStart(2, "0");
  }

  function tickTimer() {
    if (micState !== "recording") return;
    micStatus.hidden = false;
    micStatus.classList.add("rec");
    micStatus.innerHTML = '<span class="rec-dot"></span>' +
      escapeHtml(window.t("mic_recording")) + "  " + fmtTime(Date.now() - recStart);
  }

  function stopTracks() {
    if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
  }

  function clearTimers() {
    clearInterval(recTimer); recTimer = null;
    clearTimeout(maxTimer); maxTimer = null;
  }

  // ---- WAV (16 kHz mono PCM16) encoder ----
  async function toWav16k(blob) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioCtx();
    let decoded;
    try {
      decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    } finally {
      try { ctx.close(); } catch (e) {}
    }
    const rate = 16000;
    const frames = Math.max(1, Math.ceil(decoded.duration * rate));
    const off = new OfflineAudioContext(1, frames, rate);   // 1 ch = auto downmix
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start();
    const pcm = (await off.startRendering()).getChannelData(0);

    const buf = new ArrayBuffer(44 + pcm.length * 2);
    const dv = new DataView(buf);
    const put = (o, str) => { for (let i = 0; i < str.length; i++) dv.setUint8(o + i, str.charCodeAt(i)); };
    put(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); put(8, "WAVE");
    put(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true);
    dv.setUint16(22, 1, true); dv.setUint32(24, rate, true);
    dv.setUint32(28, rate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
    put(36, "data"); dv.setUint32(40, pcm.length * 2, true);
    let o = 44;
    for (let i = 0; i < pcm.length; i++, o += 2) {
      const v = Math.max(-1, Math.min(1, pcm[i]));
      dv.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    }
    return new Blob([dv], { type: "audio/wav" });
  }

  // ---- insert transcribed text at the caret ----
  function insertAtCaret(el, text) {
    const start = el.selectionStart, end = el.selectionEnd;
    const before = el.value.slice(0, start), after = el.value.slice(end);
    const sep = (before && !/\s$/.test(before)) ? " " : "";
    el.value = before + sep + text + after;
    const pos = (before + sep + text).length;
    el.setSelectionRange(pos, pos);
    el.focus();
    updateCounter();
  }

  async function sendForTranscription(wav) {
    setMicState("busy", window.t("mic_transcribing"));
    try {
      const fd = new FormData();
      fd.append("audio", wav, "speech.wav");
      const forced = textLang.value;          // follows the Text-language picker
      if (forced) fd.append("lang", forced);

      const res = await fetch("/api/transcribe", { method: "POST", body: fd });
      if (res.status === 401) { window.location = "/login"; return; }
      const data = await res.json().catch(() => ({}));

      if (res.status === 429) { toast(window.t("rate_limited"), "err"); return; }
      if (!res.ok || data.ok === false) {
        toast(data.message_en || window.t("mic_failed"), "err");
        return;
      }
      const text = (data.text || "").trim();
      if (!text) { toast(window.t("mic_nospeech"), ""); return; }
      insertAtCaret(input, text);
      toast(window.t("mic_inserted"), "ok");
    } catch (err) {
      toast(window.t("mic_failed") + ": " + err.message, "err");
    } finally {
      setMicState("idle", "");
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      toast(window.t("mic_unsupported"), "err"); return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true,
                 noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      toast(window.t("mic_denied"), "err"); return;
    }

    chunks = [];
    // Pick whatever this browser can record; we re-encode to WAV afterwards.
    let opts = {};
    for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
      if (window.MediaRecorder.isTypeSupported && window.MediaRecorder.isTypeSupported(m)) {
        opts = { mimeType: m }; break;
      }
    }
    try { mediaRecorder = new MediaRecorder(mediaStream, opts); }
    catch (e) { mediaRecorder = new MediaRecorder(mediaStream); }

    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      clearTimers(); stopTracks();
      const raw = new Blob(chunks, { type: chunks[0] ? chunks[0].type : "audio/webm" });
      chunks = [];
      if (!raw.size) { setMicState("idle", ""); toast(window.t("mic_nospeech"), ""); return; }
      setMicState("busy", window.t("mic_transcribing"));
      try {
        const wav = await toWav16k(raw);
        await sendForTranscription(wav);
      } catch (err) {
        setMicState("idle", "");
        toast(window.t("mic_failed") + ": " + err.message, "err");
      }
    };

    mediaRecorder.start();
    recStart = Date.now();
    setMicState("recording", window.t("mic_recording"));
    tickTimer();
    recTimer = setInterval(tickTimer, 500);
    maxTimer = setTimeout(() => {
      if (micState === "recording") { toast(window.t("mic_maxlen"), ""); stopRecording(); }
    }, MAX_REC_MS);
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    else { clearTimers(); stopTracks(); setMicState("idle", ""); }
  }

  window.toggleMic = function () {
    if (micState === "busy") return;
    if (micState === "recording") stopRecording();
    else startRecording();
  };

  // Stop cleanly if the user navigates away mid-recording.
  window.addEventListener("beforeunload", () => { clearTimers(); stopTracks(); });

  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); window.checkText(); }
  });

  // Initial counter (after i18n applies on DOMContentLoaded).
  document.addEventListener("DOMContentLoaded", updateCounter);
})();
