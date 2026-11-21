/* Gráficos (Chart.js local). Cada <canvas data-chart='{json}'> descreve um gráfico; cores vêm dos tokens CSS. */
(function () {
  "use strict";
  if (!window.Chart) return;
  var css = getComputedStyle(document.documentElement);
  var tok = function (n) { return css.getPropertyValue(n).trim(); };
  var palette = [tok("--color-accent"), tok("--color-ink"), "#8a93c4", tok("--color-faint"), tok("--color-success"), "#b9a98f", tok("--color-warning"), tok("--color-danger")];
  Chart.defaults.font.family = tok("--font-body");
  Chart.defaults.color = tok("--color-muted");
  Chart.defaults.borderColor = tok("--color-line-soft");
  var brl = function (cents) { return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); };

  document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
    var cfg;
    try { cfg = JSON.parse(canvas.getAttribute("data-chart")); } catch (e) { return; }
    var doughnut = cfg.type === "doughnut", multi = cfg.datasets.length > 1;
    var datasets = cfg.datasets.map(function (d, i) {
      var color = (multi && cfg.type !== "doughnut") ? palette[i] : palette[0];
      var ds = { label: d.label, data: d.data };
      if (doughnut) { ds.backgroundColor = cfg.labels.map(function (_, k) { return palette[k % palette.length]; }); ds.borderWidth = 2; ds.borderColor = tok("--color-surface"); }
      else if (cfg.type === "line") { ds.borderColor = color; ds.backgroundColor = color; ds.tension = 0.3; ds.pointRadius = 4; ds.spanGaps = true; }
      else { ds.backgroundColor = color; ds.borderRadius = 6; ds.maxBarThickness = 38; }
      return ds;
    });
    var scales = doughnut ? {} : { x: { grid: { display: false } }, y: { beginAtZero: true, suggestedMax: cfg.max, ticks: { precision: 0 } } };
    if (cfg.money && !doughnut) scales.y.ticks = { callback: function (v) { return brl(v); } };
    if (cfg.horizontal) { scales = { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { grid: { display: false } } }; }
    new Chart(canvas, {
      type: cfg.type, data: { labels: cfg.labels, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: cfg.horizontal ? "y" : "x", scales: scales,
        plugins: { legend: { display: multi || doughnut, position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: { callbacks: cfg.money ? { label: function (c) { return c.dataset.label + ": " + brl(c.parsed.y); } } : {} } }
      }
    });
  });
})();
