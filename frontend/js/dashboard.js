import { fetchStats, fetchEmissions } from './api.js';

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

// ── ANIMATION CHIFFRES ────────────────────────────
// Garde 2 décimales pour les petites valeurs (tonnes), 0 pour les grands entiers (score)
function animerChiffre(element, valeurFinale, dureeMs = 900) {
  if (!element) return;
  const debut    = Date.now();
  const decimales = valeurFinale < 100 ? 2 : 0;

  function etape() {
    const progression = Math.min((Date.now() - debut) / dureeMs, 1);
    const valeur = valeurFinale * progression;
    element.textContent = valeur.toLocaleString('fr-FR', {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales
    });
    if (progression < 1) requestAnimationFrame(etape);
  }
  requestAnimationFrame(etape);
}

function transformerSummary(summary) {
  if (!summary || !summary.details) return null;

  const details = summary.details;
  let scope1Kg = 0;
  let scope2Kg = 0;
  details.forEach(function(d) {
    if (d.scope === 1) scope1Kg += (d.total_co2_kg || 0);
    if (d.scope === 2) scope2Kg += (d.total_co2_kg || 0);
  });

  const par_source = details.map(function(d) {
    return { source: d.source, total_co2_kg: d.total_co2_kg || 0 };
  });

  return {
    total_co2_kg:     summary.total_co2_kg,
    total_co2_tonnes: summary.total_co2_tonnes,
    scope1_tonnes:    scope1Kg / 1000,
    scope2_tonnes:    scope2Kg / 1000,
    par_source:       par_source,
    statut_cbam:      summary.total_co2_tonnes < 12000 ? 'CONFORME' : 'NON CONFORME',
    details:          details
  };
}


// ── MISE À JOUR KPIs ──────────────────────────────
function updateKPIs(stats) {
  if (!stats) return;

  const total  = stats.total_co2_tonnes ?? 0;
  const scope1 = stats.scope1_tonnes    ?? 0;
  const scope2 = stats.scope2_tonnes    ?? 0;

  const conforme = stats.statut_cbam === 'CONFORME';
  const score = conforme ? 87 : 42;

  animerChiffre(document.getElementById('kpi-total'),  total);
  animerChiffre(document.getElementById('kpi-scope1'), scope1);
  animerChiffre(document.getElementById('kpi-scope2'), scope2);
  document.getElementById('kpi-score').textContent = score;

  // Badge CBAM dans la topbar
  const badge = document.getElementById('cbam-badge');
  if (badge) {
    badge.className = 'topbar__badge ' + (conforme ? 'topbar__badge--ok' : 'topbar__badge--nok');
    badge.innerHTML = conforme
      ? '<span class="point-vert"></span> CBAM CONFORME ✅'
      : '<span class="point-rouge"></span> CBAM NON CONFORME ❌';
  }

  // Badge score dans la KPI card
  const badgeScore = document.getElementById('badge-score');
  if (badgeScore) {
    badgeScore.textContent = conforme ? 'CONFORME' : 'NON CONFORME';
    badgeScore.className   = 'kpi__statut ' + (conforme ? 'kpi__statut--ok' : 'kpi__statut--nok');
  }
}

// ── UTILITAIRE GRAPHIQUES ─────────────────────────
// Détruit l'ancien graphique sur ce canvas avant d'en créer un nouveau
function resetChart(elementId) {
  const existant = Chart.getChart(elementId);
  if (existant) existant.destroy();
  return document.getElementById(elementId);
}

// ── GRAPHIQUE LIGNE — Évolution par mois ──────────
function drawEmissionsChart(emissions) {
  if (!emissions?.par_mois || emissions.par_mois.length === 0) return;

  const labels = emissions.par_mois.map(function(d) { return d.mois; });
  const scope1 = emissions.par_mois.map(function(d) { return d.scope1_kg ?? 0; });
  const scope2 = emissions.par_mois.map(function(d) { return d.scope2_kg ?? 0; });

  new Chart(resetChart('chartEmissions'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Scope 1',
          data: scope1,
          borderColor: COULEURS.orange,
          backgroundColor: COULEURS.orange + '18',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: COULEURS.orange,
          fill: true,
          tension: 0.4
        },
        {
          label: 'Scope 2',
          data: scope2,
          borderColor: COULEURS.bleu,
          backgroundColor: COULEURS.bleu + '18',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: COULEURS.bleu,
          fill: true,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'top',
          align: 'end',
          labels: { color: COULEURS.texte, font: { family: 'Consolas', size: 11 }, boxWidth: 12 }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return ctx.dataset.label + ' : ' + ctx.parsed.y.toLocaleString('fr-FR') + ' kg CO₂';
            }
          }
        }
      },
      scales: { x: STYLE_AXE, y: STYLE_AXE }
    }
  });
}

// ── GRAPHIQUE DONUT ───────────────────────────────
function drawSourceChart(stats) {
  if (!stats?.par_source) return;

  const labels  = stats.par_source.map(d => d.source);
  const valeurs = stats.par_source.map(d => d.total_co2_kg ?? 0);
  const mapCouleurs = { electricity: COULEURS.bleu, fuel: COULEURS.orange, gas: COULEURS.vert };
  const couleurs = labels.map(function(l) { return mapCouleurs[l] || COULEURS.texte; });

  new Chart(resetChart('chartSource'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: valeurs,
        backgroundColor: couleurs,
        borderColor: COULEURS.fond,
        borderWidth: 3
      }]
    },
    options: {
      responsive: true,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: COULEURS.texte,
            padding: 12,
            font: { family: 'Consolas', size: 11 },
            boxWidth: 10
          }
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct   = ((ctx.parsed / total) * 100).toFixed(1);
              return ctx.label + ' : ' + ctx.parsed.toLocaleString('fr-FR') + ' kg (' + pct + '%)';
            }
          }
        }
      }
    }
  });
}

// ── TABLEAU FLUX EN DIRECT ────────────────────────
function updateFluxTable(emissions) {
  const tbody = document.getElementById('flux-tbody');
  if (!tbody) return;

  const liste = emissions?.activities || [];

  if (liste.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#7a9e8a;padding:20px;">Aucune activité enregistrée</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  liste.slice(0, 5).forEach(function(a) {
    const co2Kg = parseFloat(a.co2_kg) || 0;
    const badge = co2Kg > 5000
      ? '<span class="badge badge-warn">⚠️ Élevé</span>'
      : '<span class="badge badge-ok">✅ Normal</span>';

    const dateFormatee = a.date
      ? new Date(a.date).toLocaleDateString('fr-FR', { day:'2-digit', month:'short', year:'numeric' })
      : '—';

    tbody.innerHTML +=
      '<tr>' +
        '<td>' + (a.source ?? '—') + '</td>' +
        '<td style="font-family:Consolas">' + (a.quantity ?? '—') + ' ' + (a.unit ?? '') + '</td>' +
        '<td>' + dateFormatee + '</td>' +
        '<td style="font-family:Consolas;color:#3fb950">' + (co2Kg/1000).toFixed(3) + ' t</td>' +
        '<td>' + badge + '</td>' +
      '</tr>';
  });
}

// ── LOADER ────────────────────────────────────────
function afficherLoader(visible) {
  let loader = document.getElementById('loader-dashboard');
  if (visible && !loader) {
    loader = document.createElement('div');
    loader.id = 'loader-dashboard';
    loader.style.cssText =
      'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);' +
      'background:#0f2018;border:1px solid #1a3828;border-radius:12px;' +
      'padding:24px 32px;color:#7a9e8a;font-family:Consolas;font-size:14px;z-index:999;';
    loader.textContent = '⟳ Chargement des données...';
    document.body.appendChild(loader);
  }
  if (loader) loader.style.display = visible ? 'block' : 'none';
}

// ── INIT PRINCIPALE ───────────────────────────────
async function initDashboard() {
  afficherLoader(true);

  // On récupère les 2 endpoints en parallèle pour aller plus vite
  const [stats, emissions] = await Promise.all([
    fetchStats(),       // /summary  → KPIs + donut
    fetchEmissions()    // /emissions → ligne chart + tableau
  ]);

  afficherLoader(false);

  const donnees = transformerSummary(stats);

  updateKPIs(donnees);           // KPIs avec décimales
  drawEmissionsChart(emissions); // ligne par mois (Scope 1 / Scope 2)
  drawSourceChart(donnees);      // donut par source
  updateFluxTable(emissions);    // tableau avec co2_kg réel
}

// ── LANCEMENT ─────────────────────────────────────
initDashboard();
setInterval(initDashboard, 30000);