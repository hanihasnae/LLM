import { fetchStats, fetchEmissions, fetchScope3Summary } from './api.js';

// ── COULEURS ──────────────────────────────────────
const COULEURS = {
  vert:   '#3fb950',
  orange: '#f78166',
  bleu:   '#58a6ff',
  violet: '#bc8cff',
  fond:   '#0f2018',
  texte:  '#7a9e8a'
};

const STYLE_AXE = {
  ticks: { color: COULEURS.texte, font: { family: 'Consolas', size: 11 } },
  grid:  { color: '#1a382840' }
};

// ── ÉTAT GLOBAL ───────────────────────────────────
let _allParMois    = [];
let _dashStats     = null;
let _scope3Summary = null;
let _prevDonutHash = '';

// ── CHIFFRES ──────────────────────────────────────
function animerChiffre(element, valeurFinale) {
  if (!element) return;
  element.dataset.valeur = valeurFinale;
  element.textContent = valeurFinale.toLocaleString('fr-FR', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3
  });
}

function transformerSummary(summary) {
  if (!summary || !summary.details) return null;

  const scope1Kg = summary.scope1_kg ?? 0;
  const scope2Kg = summary.scope2_kg ?? 0;
  const scope3Kg = summary.scope3_kg ?? 0;

  const scope1Tonnes = parseFloat((scope1Kg / 1000).toFixed(3));
  const scope2Tonnes = parseFloat((scope2Kg / 1000).toFixed(3));
  const scope3Tonnes = parseFloat((scope3Kg / 1000).toFixed(3));
  const totalTonnes  = parseFloat((scope1Tonnes + scope2Tonnes + scope3Tonnes).toFixed(3));

  const par_source = summary.details.map(function(d) {
    return { source: d.source, total_co2_kg: d.total_co2_kg || 0, scope: d.scope };
  });

  return {
    total_co2_kg:     summary.total_co2_kg,
    total_co2_tonnes: totalTonnes,
    scope1_tonnes:    scope1Tonnes,
    scope2_tonnes:    scope2Tonnes,
    scope3_tonnes:    scope3Tonnes,
    par_source:       par_source,
    details:          summary.details
  };
}

// ── KPIs + HERO BAR ───────────────────────────────
function updateKPIs(stats) {
  if (!stats) return;

  const total  = stats.total_co2_tonnes ?? 0;
  const scope1 = stats.scope1_tonnes    ?? 0;
  const scope2 = stats.scope2_tonnes    ?? 0;
  const scope3 = stats.scope3_tonnes    ?? 0;

  animerChiffre(document.getElementById('kpi-total'),  total);
  animerChiffre(document.getElementById('kpi-scope1'), scope1);
  animerChiffre(document.getElementById('kpi-scope2'), scope2);
  animerChiffre(document.getElementById('kpi-scope3'), scope3);

  if (total > 0) {
    const p1 = (scope1 / total * 100).toFixed(1);
    const p2 = (scope2 / total * 100).toFixed(1);
    const p3 = (scope3 / total * 100).toFixed(1);
    const b1 = document.getElementById('hero-bar-s1');
    const b2 = document.getElementById('hero-bar-s2');
    const b3 = document.getElementById('hero-bar-s3');
    if (b1) b1.style.width = p1 + '%';
    if (b2) b2.style.width = p2 + '%';
    if (b3) b3.style.width = p3 + '%';
    const e1 = document.getElementById('hero-pct-s1');
    const e2 = document.getElementById('hero-pct-s2');
    const e3 = document.getElementById('hero-pct-s3');
    if (e1) e1.textContent = p1 + '%';
    if (e2) e2.textContent = p2 + '%';
    if (e3) e3.textContent = p3 + '%';
  }
}

// ── INITIALISATION DATES (1er chargement) ─────────
function initDateRange() {
  const debutEl = document.getElementById('dash-date-debut');
  const finEl   = document.getElementById('dash-date-fin');
  if (!debutEl || !finEl || debutEl.value) return; // déjà rempli

  const fin = new Date();
  const debut = new Date();
  debut.setDate(debut.getDate() - 180); // 6M par défaut

  const toISO = function(d) { return d.toISOString().substring(0, 10); };
  debutEl.value = toISO(debut);
  finEl.value   = toISO(fin);
}

// ── BOUTON PÉRIODE (7j / 3M / 6M / 9M / 1an) ─────
function dashPeriode(btn, days) {
  // Active le bouton cliqué
  document.querySelectorAll('.dash-periode-btn').forEach(function(b) {
    b.classList.remove('dash-periode-btn--actif');
  });
  btn.classList.add('dash-periode-btn--actif');

  // Calcule et remplit les dates
  const fin   = new Date();
  const debut = new Date();
  debut.setDate(debut.getDate() - days);
  const toISO = function(d) { return d.toISOString().substring(0, 10); };
  const debutEl = document.getElementById('dash-date-debut');
  const finEl   = document.getElementById('dash-date-fin');
  if (debutEl) debutEl.value = toISO(debut);
  if (finEl)   finEl.value   = toISO(fin);

  dashApplyFilters();
}

// ── CHANGEMENT MANUEL DE DATES ────────────────────
function dashDateChange() {
  // Désélectionne les boutons période
  document.querySelectorAll('.dash-periode-btn').forEach(function(b) {
    b.classList.remove('dash-periode-btn--actif');
  });
  dashApplyFilters();
}

// ── HELPER : ISO "YYYY-MM" ─────────────────────────
function toYM(s) {
  if (!s) return '';
  return String(s).substring(0, 7); // "2026-01"
}

// ── FILTRE + GRAPHIQUE LIGNE ───────────────────────
function dashApplyFilters() {
  if (!_allParMois || _allParMois.length === 0) return;

  const debutVal = document.getElementById('dash-date-debut')?.value || '';
  const finVal   = document.getElementById('dash-date-fin')?.value   || '';

  let slice;
  if (debutVal && finVal) {
    const ymDebut = toYM(debutVal);
    const ymFin   = toYM(finVal);
    slice = _allParMois.filter(function(d) {
      const ym = toYM(d.mois_date);
      return ym >= ymDebut && ym <= ymFin;
    });
    // Fallback : si aucun mois dans la plage, on montre tout
    if (slice.length === 0) slice = _allParMois;
  } else {
    slice = _allParMois;
  }

  // Scopes cochés
  const s1on = document.getElementById('f-s1')?.checked ?? true;
  const s2on = document.getElementById('f-s2')?.checked ?? true;
  const s3on = document.getElementById('f-s3')?.checked ?? true;

  const labels = slice.map(function(d) { return d.mois; });
  const scope1 = slice.map(function(d) { return s1on ? (d.scope1_kg ?? 0) : null; });
  const scope2 = slice.map(function(d) { return s2on ? (d.scope2_kg ?? 0) : null; });
  const scope3 = slice.map(function(d) { return s3on ? (d.scope3_kg ?? 0) : null; });

  const existant = Chart.getChart('chartEmissions');
  if (existant) {
    existant.data.labels           = labels;
    existant.data.datasets[0].data = scope1;
    existant.data.datasets[1].data = scope2;
    existant.data.datasets[2].data = scope3;
    existant.data.datasets[0].hidden = !s1on;
    existant.data.datasets[1].hidden = !s2on;
    existant.data.datasets[2].hidden = !s3on;
    existant.update('active');
  } else {
    _createEmissionsChart(labels, scope1, scope2, scope3);
  }

  // Donut selon scopes actifs
  const actifs = [];
  if (s1on) actifs.push(1);
  if (s2on) actifs.push(2);
  if (s3on) actifs.push(3);
  renderScopeDonut(_dashStats, actifs);
}

// ── GRAPHIQUE LIGNE (création) ────────────────────
function _createEmissionsChart(labels, scope1, scope2, scope3) {
  const ctx = document.getElementById('chartEmissions');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Scope 1',
          data: scope1,
          borderColor: COULEURS.orange,
          backgroundColor: COULEURS.orange + '18',
          borderWidth: 2, pointRadius: 4,
          pointBackgroundColor: COULEURS.orange,
          fill: true, tension: 0.4
        },
        {
          label: 'Scope 2',
          data: scope2,
          borderColor: COULEURS.bleu,
          backgroundColor: COULEURS.bleu + '18',
          borderWidth: 2, pointRadius: 4,
          pointBackgroundColor: COULEURS.bleu,
          fill: true, tension: 0.4
        },
        {
          label: 'Scope 3',
          data: scope3,
          borderColor: COULEURS.violet,
          backgroundColor: COULEURS.violet + '18',
          borderWidth: 2, pointRadius: 4,
          pointBackgroundColor: COULEURS.violet,
          fill: true, tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top', align: 'end',
          labels: { color: COULEURS.texte, font: { family: 'Consolas', size: 11 }, boxWidth: 12 }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              if (ctx.parsed.y === null) return null;
              return ctx.dataset.label + ' : ' + ctx.parsed.y.toLocaleString('fr-FR') + ' kg CO₂';
            }
          }
        }
      },
      scales: { x: STYLE_AXE, y: STYLE_AXE }
    }
  });
}

// ── DONUT SCOPES ──────────────────────────────────
function renderScopeDonut(stats, activeScopes) {
  const ctx = document.getElementById('scopes-chart');
  if (!ctx || !stats) return;

  activeScopes = (activeScopes && activeScopes.length > 0) ? activeScopes : [1, 2, 3];

  let labels = [], valeurs = [], couleurs = [], titre = '';

  if (activeScopes.length === 3) {
    labels   = ['Scope 1 — Directes', 'Scope 2 — Électricité', 'Scope 3 — Chaîne de valeur'];
    valeurs  = [stats.scope1_tonnes ?? 0, stats.scope2_tonnes ?? 0, stats.scope3_tonnes ?? 0];
    couleurs = [COULEURS.orange, COULEURS.bleu, COULEURS.violet];
    titre    = 'Répartition — 3 Scopes';
  } else if (activeScopes.length === 1 && activeScopes[0] === 1) {
    const src = (stats.par_source || []).filter(function(d) { return d.scope === 1; });
    labels   = src.map(function(d) { return d.source; });
    valeurs  = src.map(function(d) { return parseFloat(((d.total_co2_kg || 0) / 1000).toFixed(3)); });
    couleurs = [COULEURS.orange, '#ff9966', '#ffcc44'];
    titre    = 'Scope 1 — par source';
  } else if (activeScopes.length === 1 && activeScopes[0] === 2) {
    const src = (stats.par_source || []).filter(function(d) { return d.scope === 2; });
    labels   = src.map(function(d) { return d.source; });
    valeurs  = src.map(function(d) { return parseFloat(((d.total_co2_kg || 0) / 1000).toFixed(3)); });
    couleurs = [COULEURS.bleu, '#44aaff', '#88ccff'];
    titre    = 'Scope 2 — par source';
  } else if (activeScopes.length === 1 && activeScopes[0] === 3) {
    const up   = _scope3Summary ? parseFloat((_scope3Summary.upstream_co2_kg   / 1000).toFixed(3)) : 0;
    const down = _scope3Summary ? parseFloat((_scope3Summary.downstream_co2_kg / 1000).toFixed(3)) : 0;
    labels   = ['Upstream (amont)', 'Downstream (aval)'];
    valeurs  = [up, down];
    couleurs = [COULEURS.violet, '#dd88ff'];
    titre    = 'Scope 3 — amont / aval';
  } else {
    const map = { 1: stats.scope1_tonnes ?? 0, 2: stats.scope2_tonnes ?? 0, 3: stats.scope3_tonnes ?? 0 };
    const nameMap  = { 1: 'Scope 1', 2: 'Scope 2', 3: 'Scope 3' };
    const colorMap = { 1: COULEURS.orange, 2: COULEURS.bleu, 3: COULEURS.violet };
    activeScopes.forEach(function(s) {
      labels.push(nameMap[s]);
      valeurs.push(map[s]);
      couleurs.push(colorMap[s]);
    });
    titre = 'Scopes sélectionnés';
  }

  const titreEl = document.getElementById('dash-donut-titre');
  if (titreEl) titreEl.textContent = titre;

  const hash = JSON.stringify({ labels, valeurs });
  if (hash === _prevDonutHash) return;
  _prevDonutHash = hash;

  if (window.scopesChart) { window.scopesChart.destroy(); window.scopesChart = null; }

  window.scopesChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: valeurs,
        backgroundColor: couleurs,
        borderColor: COULEURS.fond,
        borderWidth: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: COULEURS.texte, font: { family: 'Consolas', size: 11 }, padding: 14, boxWidth: 12 }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
              const pct   = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : '0.0';
              return ctx.label + ' : ' + ctx.parsed.toLocaleString('fr-FR', {
                minimumFractionDigits: 3, maximumFractionDigits: 3
              }) + ' t (' + pct + '%)';
            }
          }
        }
      }
    }
  });
}

// ── LOADER ────────────────────────────────────────
let premiereCharge = true;

function afficherLoader(visible) { /* loader supprimé */ }

// ── INIT ──────────────────────────────────────────
let estEnChargement = false;

async function initDashboard() {
  if (estEnChargement) return;
  estEnChargement = true;

  if (premiereCharge) afficherLoader(true);

  try {
    const [stats, emissions, scope3] = await Promise.all([
      fetchStats(),
      fetchEmissions(),
      fetchScope3Summary()
    ]);

    const donnees = transformerSummary(stats);
    if (!donnees) return;

    _dashStats     = donnees;
    _scope3Summary = scope3;
    if (emissions?.par_mois) _allParMois = emissions.par_mois;

    updateKPIs(donnees);

    // Affiche l'heure de dernière mise à jour
    const el = document.getElementById('last-update');
    if (el) {
      const h = new Date();
      el.textContent = 'Màj ' + h.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // Initialise les dates au 1er chargement puis applique les filtres
    initDateRange();
    dashApplyFilters();

  } finally {
    if (premiereCharge) {
      afficherLoader(false);
      premiereCharge = false;
    }
    estEnChargement = false;
  }
}

// ── LANCEMENT ─────────────────────────────────────
initDashboard();
setInterval(initDashboard, 5000);

// Exposition globale pour les handlers HTML onclick/onchange
window.dashApplyFilters = dashApplyFilters;
window.dashPeriode      = dashPeriode;
window.dashDateChange   = dashDateChange;
