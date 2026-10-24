/* TeamFlow front-end behaviour: theme, mobile menu, dropdowns, toasts,
   Ctrl+K search, auto-submit selects, copy buttons, chart, live notifications. */
(function () {
  "use strict";
  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  /* ---- Theme toggle ---- */
  $$("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("teamflow-theme", next); } catch (e) {}
    });
  });

  /* ---- Mobile sidebar ---- */
  var sidebar = $("#sidebar"), scrim = $("#scrim"), menuBtn = $("#menu-btn");
  function setMenu(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (scrim) scrim.hidden = !open;
    if (menuBtn) menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (menuBtn) menuBtn.addEventListener("click", function () { setMenu(!sidebar.classList.contains("open")); });
  if (scrim) scrim.addEventListener("click", function () { setMenu(false); });

  /* ---- Dropdowns ---- */
  $$("[data-dropdown]").forEach(function (dd) {
    var trigger = $("[data-dropdown-trigger]", dd), menu = $("[data-dropdown-menu]", dd);
    if (!trigger || !menu) return;
    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = menu.hidden;
      menu.hidden = !open;
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!dd.contains(e.target)) { menu.hidden = true; trigger.setAttribute("aria-expanded", "false"); }
    });
  });

  /* ---- Public landing menu ---- */
  var lnToggle = $("[data-landing-toggle]"), lnNav = $("[data-landing-nav]");
  if (lnToggle && lnNav) {
    lnToggle.addEventListener("click", function () { lnNav.classList.toggle("open"); });
    $$("a", lnNav).forEach(function (a) { a.addEventListener("click", function () { lnNav.classList.remove("open"); }); });
  }

  /* ---- Toasts ---- */
  function hideToast(t) {
    t.classList.add("hide");
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 300);
  }
  $$(".toast").forEach(function (t, i) { setTimeout(function () { hideToast(t); }, 5000 + i * 300); });
  document.addEventListener("click", function (e) {
    var c = e.target.closest("[data-toast-close]");
    if (c) hideToast(c.closest(".toast"));
  });
  function showToast(text, kind) {
    var box = $("#toast-container");
    if (!box) { box = document.createElement("div"); box.id = "toast-container"; document.body.appendChild(box); }
    var t = document.createElement("div");
    t.className = "toast toast-" + (kind || "info");
    var span = document.createElement("span"); span.className = "toast-text"; span.textContent = text;
    var btn = document.createElement("button"); btn.type = "button"; btn.className = "toast-close"; btn.setAttribute("data-toast-close", ""); btn.innerHTML = "&times;";
    t.appendChild(span); t.appendChild(btn); box.appendChild(t);
    setTimeout(function () { hideToast(t); }, 6000);
  }

  /* ---- Keyboard: Ctrl/Cmd+K focuses search ---- */
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      var s = $("#global-search");
      if (s) { e.preventDefault(); s.focus(); s.select(); }
    }
    if (e.key === "Escape") setMenu(false);
  });

  /* ---- Auto-submit selects / checkboxes ---- */
  $$("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { if (el.form) el.form.submit(); });
  });

  /* ---- Confirm dialogs on destructive forms ---- */
  $$("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault(); });
  });

  /* ---- Copy to clipboard ---- */
  $$("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var text = btn.getAttribute("data-copy");
      var done = function () { showToast(btn.getAttribute("data-copied") || "Copied", "success"); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done);
      else { var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (er) {} document.body.removeChild(ta); }
    });
  });

  /* ---- Card inputs: format number & expiry ---- */
  $$("[data-card-number]").forEach(function (el) {
    el.addEventListener("input", function () {
      var d = el.value.replace(/\D/g, "").slice(0, 19);
      el.value = d.replace(/(.{4})/g, "$1 ").trim();
    });
  });
  $$("[data-card-expiry]").forEach(function (el) {
    el.addEventListener("input", function () {
      var d = el.value.replace(/\D/g, "").slice(0, 4);
      el.value = d.length > 2 ? d.slice(0, 2) + "/" + d.slice(2) : d;
    });
  });

  /* ---- Registration: show the card section only for paid plans ---- */
  var cardSection = $("[data-card-section]");
  if (cardSection) {
    $$("input[name=plan]").forEach(function (r) {
      r.addEventListener("change", function () { cardSection.hidden = r.getAttribute("data-paid") !== "1"; });
    });
  }

  /* ---- Progress overview chart (dashboard) ---- */
  var chartEl = $("#progress-chart"), dataEl = $("#chart-data");
  if (chartEl && dataEl) {
    var series = JSON.parse(dataEl.textContent), range = "year";
    var render = function () {
      var s = series[range], max = Math.max(1, Math.max.apply(null, s.created.concat(s.done)));
      var html = "";
      for (var i = 0; i < s.labels.length; i++) {
        html += '<div class="bar-col" title="' + s.labels[i] + ': ' + s.created[i] + ' / ' + s.done[i] + '">' +
          '<div class="bar-pair"><i class="bar b-created" style="height:' + (s.created[i] / max * 100) + '%"></i>' +
          '<i class="bar b-done" style="height:' + (s.done[i] / max * 100) + '%"></i></div>' +
          '<span class="bar-label">' + s.labels[i] + '</span></div>';
      }
      chartEl.innerHTML = html;
      chartEl.className = "bars bars-" + range;
    };
    $$("[data-range]").forEach(function (b) {
      b.addEventListener("click", function () {
        range = b.getAttribute("data-range");
        $$("[data-range]").forEach(function (x) { x.classList.toggle("active", x === b); });
        render();
      });
    });
    render();
  }

  /* ---- Live notifications over WebSocket ---- */
  if (window.TEAMFLOW_WS) {
    var tries = 0;
    var bump = function () {
      $$("[data-notif-badge]").forEach(function (b) { b.textContent = (parseInt(b.textContent, 10) || 0) + 1; b.hidden = false; });
      $$("[data-notif-badge-dot]").forEach(function (d) { d.hidden = false; });
    };
    var connect = function () {
      var proto = location.protocol === "https:" ? "wss://" : "ws://";
      var ws;
      try { ws = new WebSocket(proto + location.host + "/ws/notifications/"); } catch (e) { return; }
      ws.onmessage = function (ev) {
        var data; try { data = JSON.parse(ev.data); } catch (e) { return; }
        if (data.type === "notification" && data.payload) {
          bump(); showToast(data.payload.title + ": " + data.payload.message, "info");
        }
      };
      ws.onopen = function () { tries = 0; };
      ws.onclose = function (ev) { if (ev.code !== 4001 && ++tries <= 3) setTimeout(connect, 4000 * tries); };
    };
    connect();
  }
})();
