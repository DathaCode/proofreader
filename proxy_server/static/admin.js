/* Sinhala Proofreader - Proxy Admin (v5) client script.
   Theme toggle, toast dismissal, delete confirmations, theme-aware charts,
   and the dashboard's live "who is online" polling. No dependencies besides
   the locally bundled Chart.js. */
(function () {
  "use strict";
  var root = document.documentElement;

  // ----------------------------------------------------------- theme
  function storedTheme() {
    try { return localStorage.getItem("pa-theme"); } catch (e) { return null; }
  }
  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    var label = document.getElementById("theme-label");
    if (label) label.textContent = t === "dark" ? "Light mode" : "Dark mode";
  }
  var initial = storedTheme() ||
    (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(initial);
  // This script runs in <head>; label the toggle once the sidebar exists.
  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(root.getAttribute("data-theme") || initial);
  });

  window.PA = window.PA || {};
  PA.toggleTheme = function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("pa-theme", next); } catch (e) {}
    PA.redrawCharts();
  };

  // ----------------------------------------------------------- toasts
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-dismiss]");
    if (b) b.parentElement.remove();
  });
  window.addEventListener("load", function () {
    document.querySelectorAll(".flash.ok").forEach(function (el) {
      setTimeout(function () { el.style.transition = "opacity .4s"; el.style.opacity = 0;
        setTimeout(function () { el.remove(); }, 450); }, 5000);
    });
  });

  // ------------------------------------------------- confirm dialogs
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // auto-submit filter selects
  document.addEventListener("change", function (e) {
    if (e.target.matches("[data-autosubmit]")) e.target.form.submit();
  });

  // ----------------------------------------------------------- charts
  function css(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
  PA.palette = function () {
    return {
      primary: css("--primary"), success: css("--success"), warning: css("--warning"),
      danger: css("--danger"), violet: css("--violet"), muted: css("--muted"),
      border: css("--border"), text: css("--text-2"), surface: css("--surface")
    };
  };
  PA.alpha = function (hex, a) {
    if (!hex || hex[0] !== "#") return hex;
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
  };

  var registry = [];   // [{el, build}] so charts can be rebuilt on theme change
  PA.chart = function (id, build) {
    var el = document.getElementById(id);
    if (!el || !window.Chart) return;
    var entry = { el: el, build: build, chart: null };
    registry.push(entry);
    draw(entry);
  };
  function draw(entry) {
    if (entry.chart) entry.chart.destroy();
    var p = PA.palette();
    Chart.defaults.color = p.muted;
    Chart.defaults.borderColor = p.border;
    Chart.defaults.font.family = css("--font") || "Segoe UI, sans-serif";
    Chart.defaults.font.size = 12;
    var cfg = entry.build(p);
    cfg.options = cfg.options || {};
    cfg.options.responsive = true;
    cfg.options.maintainAspectRatio = false;
    cfg.options.plugins = cfg.options.plugins || {};
    cfg.options.plugins.tooltip = Object.assign({
      backgroundColor: p.surface, titleColor: p.text, bodyColor: p.text,
      borderColor: p.border, borderWidth: 1, padding: 10, cornerRadius: 8,
      boxPadding: 4, usePointStyle: true
    }, cfg.options.plugins.tooltip || {});
    entry.chart = new Chart(entry.el, cfg);
  }
  PA.redrawCharts = function () { registry.forEach(draw); };

  PA.money = function (v) {
    v = Number(v || 0);
    if (v === 0) return "$0";
    if (v < 0.01) return "$" + v.toFixed(4);
    return "$" + v.toFixed(2);
  };
  PA.grid = function (p) {
    return { grid: { color: PA.alpha(p.border, 0.9) || p.border, drawTicks: false },
             border: { display: false }, ticks: { padding: 8 } };
  };

  // ------------------------------------------------- live dashboard
  PA.live = function (url) {
    var list = document.getElementById("live-list");
    if (!list) return;
    function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
    function tick() {
      fetch(url, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (d) {
        var count = document.getElementById("live-count");
        if (count) count.textContent = d.online.length;
        if (!d.online.length) {
          list.innerHTML = '<li class="muted">No client app is open right now.</li>';
        } else {
          list.innerHTML = d.online.map(function (c) {
            return '<li><span class="pulse"></span><div class="who"><a href="' + c.url + '">' +
              esc(c.name) + '</a><div class="meta">' + esc(c.ip) +
              (c.version ? " &middot; v" + esc(c.version) : "") + '</div></div>' +
              '<span class="meta">' + esc(c.ago) + '</span></li>';
          }).join("");
        }
        ["requests", "words", "cost"].forEach(function (k) {
          var el = document.getElementById("today-" + k);
          if (el) el.textContent = d.today[k];
        });
        var t = document.getElementById("live-time");
        if (t) t.textContent = "updated " + d.time;
      }).catch(function () {
        var t = document.getElementById("live-time");
        if (t) t.textContent = "offline - retrying";
      });
    }
    setInterval(tick, 15000);
  };
})();
