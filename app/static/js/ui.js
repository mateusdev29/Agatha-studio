/* Componentes de interface: modal, confirmação, avisos (toasts) e estado de carregamento. */
(function () {
  "use strict";

  /* ---------- Modal genérico: data-modal-open="id" / data-modal-close ---------- */
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-modal-open]");
    if (opener) {
      var dlg = document.getElementById(opener.getAttribute("data-modal-open"));
      if (dlg && dlg.showModal) dlg.showModal();
      return;
    }
    var closer = e.target.closest("[data-modal-close]");
    if (closer) { var d = closer.closest("dialog"); if (d) d.close(); return; }
    // clique no fundo (fora do conteúdo) fecha
    if (e.target.tagName === "DIALOG" && e.target.classList.contains("modal") && e.target.id !== "confirm-dialog") {
      e.target.close();
    }
  });

  /* ---------- Confirmação antes de ações destrutivas ---------- */
  var confirmDlg = document.getElementById("confirm-dialog");
  var pending = null;

  function askConfirm(source, onAccept) {
    if (!confirmDlg) { onAccept(); return; }
    var accept = document.getElementById("confirm-accept");
    document.getElementById("confirm-title").textContent = source.getAttribute("data-confirm-title") || "Confirmar ação";
    document.getElementById("confirm-message").textContent = source.getAttribute("data-confirm");
    accept.textContent = source.getAttribute("data-confirm-label") || "Confirmar";
    accept.className = "btn " + (source.getAttribute("data-confirm-tone") === "danger" ? "btn-danger" : "btn-primary");
    pending = onAccept;
    confirmDlg.showModal();
    accept.focus();
  }

  if (confirmDlg) {
    document.getElementById("confirm-accept").addEventListener("click", function () {
      var fn = pending; pending = null; confirmDlg.close();
      if (fn) fn();
    });
    confirmDlg.querySelector("[data-confirm-cancel]").addEventListener("click", function () { pending = null; confirmDlg.close(); });
    confirmDlg.addEventListener("click", function (e) { if (e.target === confirmDlg) { pending = null; confirmDlg.close(); } });
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    var submitter = e.submitter;
    var source = (submitter && submitter.hasAttribute("data-confirm")) ? submitter
               : form.hasAttribute("data-confirm") ? form : null;
    if (!source || form.dataset.confirmed === "1") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    askConfirm(source, function () {
      form.dataset.confirmed = "1";
      if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
    });
  }, true);

  /* ---------- Avisos ---------- */
  var toasts = document.getElementById("toasts");

  function dismiss(toast) { if (toast && toast.parentNode) toast.parentNode.removeChild(toast); }

  function armAutoDismiss(toast) { setTimeout(function () { dismiss(toast); }, 5000); }

  if (toasts) {
    toasts.querySelectorAll("[data-autodismiss]").forEach(armAutoDismiss);
    toasts.addEventListener("click", function (e) {
      if (e.target.closest("[data-toast-close]")) dismiss(e.target.closest(".toast"));
    });
  }

  /* API pública mínima: Studio.toast("Salvo", "success" | "error" | "info") */
  window.Studio = window.Studio || {};
  window.Studio.toast = function (message, tone) {
    if (!toasts) return;
    tone = tone || "info";
    var el = document.createElement("div");
    el.className = "toast toast-" + tone;
    el.setAttribute("role", tone === "error" ? "alert" : "status");
    var p = document.createElement("p");
    p.className = "toast-message";
    p.textContent = message;               // textContent: nunca interpreta HTML
    var b = document.createElement("button");
    b.type = "button"; b.className = "toast-close"; b.setAttribute("data-toast-close", "");
    b.setAttribute("aria-label", "Fechar aviso"); b.textContent = "×";
    el.appendChild(p); el.appendChild(b);
    toasts.appendChild(el);
    if (tone !== "error") armAutoDismiss(el);
  };

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-toast-message]");
    if (t) window.Studio.toast(t.getAttribute("data-toast-message"), t.getAttribute("data-toast-tone") || "info");
  });

  /* ---------- Select dependente: <select data-depends-on="id-do-select-pai"> com <option data-group="valor-do-pai"> ---------- */
  document.querySelectorAll("select[data-depends-on]").forEach(function (child) {
    var parent = document.getElementById(child.getAttribute("data-depends-on"));
    if (!parent) return;
    function apply() {
      var keep = false;
      Array.prototype.forEach.call(child.options, function (opt) {
        var group = opt.getAttribute("data-group");
        var visible = !group || group === parent.value;
        opt.hidden = !visible; opt.disabled = !visible;
        if (visible && opt.value === child.value) keep = true;
      });
      if (!keep) child.value = child.options[0].value;
    }
    parent.addEventListener("change", apply);
    apply();
  });

  /* ---------- Copiar texto: <button data-copy-target="id-do-textarea"> ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-target]");
    if (!btn) return;
    var el = document.getElementById(btn.getAttribute("data-copy-target"));
    if (!el) return;
    var done = function () { window.Studio.toast("Texto copiado.", "success"); };
    var fallback = function () { el.select(); try { document.execCommand("copy"); done(); } catch (err) { window.Studio.toast("Não foi possível copiar.", "error"); } };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(el.value).then(done, fallback); else fallback();
  });

  /* ---------- Carregamento: evita duplo envio e mostra progresso ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || form.method.toLowerCase() !== "post" || form.hasAttribute("data-no-loading")) return;
    var btn = e.submitter || form.querySelector("button[type=submit], input[type=submit]");
    if (!btn) return;
    form.setAttribute("aria-busy", "true");
    setTimeout(function () { btn.classList.add("is-loading"); btn.disabled = true; }, 0);
  });

  // Voltar pelo histórico (bfcache) não deve deixar botões travados
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    document.querySelectorAll(".is-loading").forEach(function (b) { b.classList.remove("is-loading"); b.disabled = false; });
    document.querySelectorAll("form[aria-busy]").forEach(function (f) { f.removeAttribute("aria-busy"); f.dataset.confirmed = "0"; });
  });
})();
