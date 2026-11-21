/* Casca da aplicação: gaveta do menu (mobile) e dropdowns do topo. Sem dependências. */
(function () {
  "use strict";

  var body = document.body;
  var sidebar = document.getElementById("sidebar");
  var mobile = window.matchMedia("(max-width: 767px)");
  var lastFocus = null;

  /* ---------- Gaveta ---------- */
  function drawerToggles() { return document.querySelectorAll("[data-drawer-toggle]"); }

  function setDrawer(open) {
    if (!sidebar) return;
    body.classList.toggle("drawer-open", open);
    drawerToggles().forEach(function (b) {
      b.setAttribute("aria-expanded", String(open));
      b.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
    });
    if (open) {
      lastFocus = document.activeElement;
      var first = sidebar.querySelector(".nav-link");
      if (first) first.focus();
    } else if (lastFocus) {
      lastFocus.focus();
      lastFocus = null;
    }
  }

  function trapFocus(e) {
    if (e.key !== "Tab" || !body.classList.contains("drawer-open")) return;
    var f = sidebar.querySelectorAll("a[href], button:not([disabled])");
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ---------- Dropdowns ---------- */
  function closeDropdowns(except) {
    document.querySelectorAll("[data-dropdown]").forEach(function (d) {
      if (d === except) return;
      var panel = d.querySelector("[data-dropdown-panel]");
      var trigger = d.querySelector("[data-dropdown-trigger]");
      if (panel && !panel.hidden) { panel.hidden = true; trigger.setAttribute("aria-expanded", "false"); }
    });
  }

  document.addEventListener("click", function (e) {
    var t = e.target;

    if (t.closest("[data-drawer-toggle]")) {
      setDrawer(!body.classList.contains("drawer-open"));
      return;
    }
    if (t.closest("[data-drawer-close]")) { setDrawer(false); return; }
    if (t.closest(".sidebar .nav-link") && mobile.matches) { body.classList.remove("drawer-open"); }

    var trigger = t.closest("[data-dropdown-trigger]");
    if (trigger) {
      var dd = trigger.closest("[data-dropdown]");
      var panel = dd.querySelector("[data-dropdown-panel]");
      var willOpen = panel.hidden;
      closeDropdowns(dd);
      panel.hidden = !willOpen;
      trigger.setAttribute("aria-expanded", String(willOpen));
      return;
    }
    if (!t.closest("[data-dropdown-panel]")) closeDropdowns(null);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (body.classList.contains("drawer-open")) setDrawer(false);
      var open = document.querySelector("[data-dropdown-panel]:not([hidden])");
      if (open) {
        var dd = open.closest("[data-dropdown]");
        closeDropdowns(null);
        dd.querySelector("[data-dropdown-trigger]").focus();
      }
    }
    trapFocus(e);
  });

  /* Ao ampliar a janela, garante que a gaveta não fique "presa" aberta */
  mobile.addEventListener("change", function (e) { if (!e.matches) body.classList.remove("drawer-open"); });
})();
