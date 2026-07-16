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
      const res = await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections }),
      });
      const data = await res.json();
      if (data.ok) { toast(window.t("saved_n", data.saved), "ok"); lastCorrectedText = edited; }
      else toast(window.t("save_failed"), "err");
    } catch (err) {
      toast(window.t("conn_error"), "err");
    }
  };

  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); window.checkText(); }
  });

  // Initial counter (after i18n applies on DOMContentLoaded).
  document.addEventListener("DOMContentLoaded", updateCounter);
})();
