/* Sinhala Proofreader Web App — main UI logic (vanilla JS). */

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

  let lastCorrectedText = "";     // the model's corrected_text (for diffing on save)

  // ---------- helpers ----------
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function toast(msg, kind) {
    const t = $("toast");
    t.textContent = msg;
    t.className = "toast show " + (kind || "");
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.className = "toast"; }, 3000);
  }

  function updateCounter() {
    const text = input.value;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    counter.innerHTML = `<b>${words}</b> වචන · <b>${text.length}</b> අකුරු`;
  }
  input.addEventListener("input", updateCounter);
  updateCounter();

  // ---------- highlight builder ----------
  const CLASS_FOR = {
    spelling: "spell-error",
    grammar: "grammar-error",
    grammar_discord: "grammar-error",
    encoding_error: "encoding-error",
  };

  function highlightErrors(text, errors) {
    // Collect located spans (start/end resolved server-side).
    const spans = errors
      .filter((e) => e.start != null && e.end != null)
      .map((e) => ({ start: e.start, end: e.end, e }))
      .sort((a, b) => a.start - b.start);

    let html = "";
    let cursor = 0;
    for (const s of spans) {
      if (s.start < cursor) continue; // skip overlaps
      html += escapeHtml(text.slice(cursor, s.start));
      const cls = CLASS_FOR[s.e.type] || "spell-error";
      const tip = `${s.e.original} → ${s.e.correction}  ·  ${s.e.explanation_si || s.e.explanation_en || ""}`;
      html += `<mark class="${cls}" title="${escapeHtml(tip)}">${escapeHtml(text.slice(s.start, s.end))}</mark>`;
      cursor = s.end;
    }
    html += escapeHtml(text.slice(cursor));
    return html || '<span class="empty">…</span>';
  }

  const ICON_FOR = {
    spelling: "🔤",
    grammar: "📝",
    grammar_discord: "📝",
    encoding_error: "🔧",
  };
  const TYPE_LABEL = {
    spelling: "අක්ෂර වින්‍යාස",
    grammar: "ව්‍යාකරණ",
    grammar_discord: "ව්‍යාකරණ",
    encoding_error: "encoding",
  };

  function renderErrorList(errors) {
    if (!errors.length) {
      errorItems.innerHTML = '<div class="empty-state">✅ දෝෂ කිසිවක් හමු නොවීය.</div>';
      return;
    }
    errorItems.innerHTML = errors.map((e) => {
      const conf = Math.round((e.confidence || 0) * 100);
      return `<div class="err ${e.type}">
        <div class="ico">${ICON_FOR[e.type] || "❗"}</div>
        <div class="body">
          <div class="change"><span class="from">${escapeHtml(e.original)}</span>
            &nbsp;→&nbsp;<span class="to">${escapeHtml(e.correction)}</span>
            <span class="tag">${TYPE_LABEL[e.type] || e.type}</span></div>
          <div class="why">${escapeHtml(e.explanation_si || e.explanation_en || "")}</div>
        </div>
        <div class="conf">${conf}%</div>
      </div>`;
    }).join("");
  }

  function renderChips(stats, preFixed) {
    if (!stats) { chips.innerHTML = ""; return; }
    const parts = [
      `<span class="chip">වචන <b>${stats.total_words || 0}</b></span>`,
      `<span class="chip">දෝෂ <b>${stats.errors_found || 0}</b></span>`,
      `<span class="chip">අක්ෂර <b>${stats.spell_errors || 0}</b></span>`,
      `<span class="chip">ව්‍යාකරණ <b>${stats.grammar_errors || 0}</b></span>`,
    ];
    if (preFixed) parts.push(`<span class="chip">පෙර-නිවැරදි <b>${preFixed}</b></span>`);
    chips.innerHTML = parts.join("");
  }

  // ---------- main actions ----------
  window.checkText = async function () {
    const text = input.value.trim();
    if (!text) { toast("කරුණාකර පෙළක් ඇතුළු කරන්න", "err"); input.focus(); return; }
    overlay.classList.add("show");
    try {
      const res = await fetch("/api/proofread", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (res.status === 401) { window.location = "/login"; return; }
      const data = await res.json();
      if (res.status === 429) { toast(data.message_si || "ඉල්ලීම් සීමාව ඉක්මවා ඇත", "err"); return; }
      if (!res.ok || data.ok === false) {
        toast((data.message_si || data.summary_si || "දෝෂයකි") , "err");
        highlighted.innerHTML = "";
        highlighted.classList.add("empty");
        return;
      }

      const original = data.original || text;
      highlighted.classList.remove("empty");
      highlighted.innerHTML = highlightErrors(original, data.errors || []);

      lastCorrectedText = data.corrected_text || original;
      corrected.value = lastCorrectedText;

      renderErrorList(data.errors || []);
      renderChips(data.stats, data.pre_fixed_count);

      const sSi = data.summary_si || "";
      summaryEl.textContent = sSi;

      const n = (data.errors || []).length;
      toast(n ? `${n} දෝෂ හමු විය` : "දෝෂ නොමැත ✅", n ? "" : "ok");
    } catch (err) {
      toast("සම්බන්ධතා දෝෂයකි: " + err.message, "err");
    } finally {
      overlay.classList.remove("show");
    }
  };

  window.clearText = function () {
    input.value = "";
    updateCounter();
    highlighted.innerHTML = "";
    highlighted.classList.add("empty");
    corrected.value = "";
    lastCorrectedText = "";
    errorItems.innerHTML = '<div class="empty-state">පෙළක් ඇතුළු කර පරීක්ෂා කරන්න.</div>';
    chips.innerHTML = "";
    summaryEl.textContent = "";
    input.focus();
  };

  window.copyCorrected = async function () {
    const text = corrected.value;
    if (!text) { toast("පිටපත් කිරීමට කිසිවක් නැත", "err"); return; }
    try {
      await navigator.clipboard.writeText(text);
      toast("පිටපත් කරන ලදී 📋", "ok");
    } catch {
      corrected.select();
      document.execCommand("copy");
      toast("පිටපත් කරන ලදී 📋", "ok");
    }
  };

  // Compare the model's corrected_text with the user's edited version,
  // word by word, and record the differences as human corrections.
  window.saveCorrections = async function () {
    const edited = corrected.value.trim();
    if (!edited) { toast("සුරැකීමට කිසිවක් නැත", "err"); return; }
    if (!lastCorrectedText) { toast("පළමුව පෙළක් පරීක්ෂා කරන්න", "err"); return; }

    const origWords = lastCorrectedText.trim().split(/\s+/);
    const newWords = edited.split(/\s+/);
    const corrections = [];
    const n = Math.min(origWords.length, newWords.length);
    for (let i = 0; i < n; i++) {
      if (origWords[i] !== newWords[i]) {
        corrections.push({ wrong: origWords[i], correct: newWords[i], type: "spelling" });
      }
    }
    if (!corrections.length) {
      toast("වෙනස්කම් හමු නොවීය", "");
      return;
    }
    const preview = corrections.slice(0, 5)
      .map((c) => `${c.wrong} → ${c.correct}`).join("\n");
    if (!confirm(`මෙම නිවැරදි කිරීම් ${corrections.length}ක් සුරකින්නද?\n\n${preview}${corrections.length > 5 ? "\n…" : ""}`)) {
      return;
    }
    try {
      const res = await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections }),
      });
      const data = await res.json();
      if (data.ok) {
        toast(`✍️ නිවැරදි කිරීම් ${data.saved}ක් සුරකින ලදී`, "ok");
        lastCorrectedText = edited;
      } else {
        toast("සුරැකීම අසාර්ථකයි", "err");
      }
    } catch (err) {
      toast("සම්බන්ධතා දෝෂයකි", "err");
    }
  };

  // Ctrl+Enter to check.
  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); window.checkText(); }
  });
})();
