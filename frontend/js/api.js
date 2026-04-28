/* ============================================================
   API.JS — Communication avec le serveur FastAPI

   Ce fichier gère TOUTES les requêtes vers notre API.
   Le reste du code n'a pas besoin de savoir comment les
   requêtes fonctionnent : il appelle juste une fonction ici.

   COMMENT ÇA MARCHE :
   → Le navigateur envoie une requête HTTP à FastAPI
   → FastAPI répond avec des données JSON
   → On retourne ces données à qui a appelé la fonction

   "async/await" = on attend la réponse sans bloquer la page.
   "try/catch"   = si quelque chose rate, on gère l'erreur.
   ============================================================ */


// Adresse du serveur FastAPI (localhost = notre propre ordinateur)
const API_BASE = "http://localhost:8000";


/* ──────────────────────────────────────────────────
   UTILITAIRE — Met à jour le badge dans la sidebar
   pour indiquer si l'API est accessible ou non.
──────────────────────────────────────────────────── */
function mettreAJourBadge(estConnecte) {
  // Cherche la zone de statut dans le pied de la sidebar
  const zoneBadge = document.querySelector('.sidebar__footer-statut');
  if (!zoneBadge) return; // ne fait rien si la sidebar n'existe pas

  if (estConnecte) {
    zoneBadge.innerHTML =
      '<span class="point-vert"></span> API connectée';
  } else {
    // Point rouge si déconnecté
    zoneBadge.innerHTML =
      '<span style="width:7px;height:7px;border-radius:50%;' +
      'background:#ff4560;display:inline-block;flex-shrink:0;"></span>' +
      ' API déconnectée';
  }
}


/* ──────────────────────────────────────────────────
   UTILITAIRE — Fonction de requête commune
   Tous les appels API passent par ici.
   Paramètres :
   - chemin  : ex "/summary", "/activities"
   - options : optionnel, pour POST (méthode, body...)
──────────────────────────────────────────────────── */
async function requete(chemin, options = {}) {
  // try = "essaie ce bloc de code"
  try {
    console.log("📡 Requête vers :", API_BASE + chemin);

    // fetch() envoie la requête et attend la réponse
    const reponse = await fetch(API_BASE + chemin, {
      headers: { "Content-Type": "application/json" },
      ...options          // fusionne avec les options supplémentaires
    });

    // Si le serveur répond avec une erreur (ex: 404, 500)
    if (!reponse.ok) {
      throw new Error("Erreur serveur : " + reponse.status);
    }

    // Convertit la réponse JSON en objet JavaScript
    const donnees = await reponse.json();
    console.log("✅ Réponse reçue :", donnees);

    mettreAJourBadge(true);  // API connectée
    return donnees;

  } catch (erreur) {
    // catch = "si une erreur se produit, fais ça"
    console.error("❌ Erreur API (" + chemin + ") :", erreur.message);
    mettreAJourBadge(false);  // API déconnectée
    return null;              // retourne null pour signaler l'échec
  }
}


/* ============================================================
   FONCTIONS PUBLIQUES — À utiliser dans les autres fichiers JS
   ============================================================ */


/* ──────────────────────────────────────────────────
   1. RÉSUMÉ DES ÉMISSIONS
   GET /summary
   Retourne : total_co2_kg, total_co2_tonnes, details
──────────────────────────────────────────────────── */
export async function fetchStats() {
  console.log("📊 Chargement du résumé des émissions...");
  return await requete("/summary");

  /*
    Réponse réelle de FastAPI /summary :
    {
      "details": [
        {
          "source"         : "Charbon",
          "total_quantity" : 2.4,
          "unit"           : "t",
          "factor"         : 2.34,
          "total_co2_kg"   : 5616.0,
          "scope"          : "Scope 1"
        },
        ...
      ],
      "total_co2_kg"     : 12450.00,
      "total_co2_tonnes" : 12.45
    }

    dashboard.js transforme cette réponse avec transformerSummary()
    pour construire par_source, scope1_tonnes, scope2_tonnes, statut_cbam.
  */
}


/* ──────────────────────────────────────────────────
   2. LISTE DES ACTIVITÉS
   GET /activities
   Retourne : liste de toutes les activités enregistrées
──────────────────────────────────────────────────── */
export async function fetchActivities() {
  console.log("⚡ Chargement des activités...");
  return await requete("/activities");

  /*
    Exemple de réponse attendue :
    [
      {
        "id"      : 1,
        "source"  : "Combustion charbon",
        "quantite": 2.4,
        "unite"   : "t",
        "date"    : "2026-01-22",
        "co2_kg"  : 5616
      },
      ...
    ]
  */
}


/* ──────────────────────────────────────────────────
   3. AJOUTER UNE ACTIVITÉ
   POST /activities
   Paramètres : source, quantite, unite, date
   Retourne   : l'activité créée avec le CO₂ calculé
──────────────────────────────────────────────────── */
export async function addActivity(source, quantite, unite, date) {
  console.log("➕ Ajout d'une activité :", source, quantite, unite);

  // JSON.stringify transforme un objet JS en texte JSON
  const corps = JSON.stringify({
    source:   source,
    quantite: quantite,
    unite:    unite,
    date:     date
  });

  return await requete("/activities", {
    method: "POST",   // POST = on envoie des données (≠ GET qui lit seulement)
    body:   corps
  });

  /*
    Exemple de réponse attendue :
    {
      "id"     : 5,
      "source" : "Gaz naturel",
      "co2_kg" : 2160,
      "message": "Activité ajoutée avec succès"
    }
  */
}


/* ──────────────────────────────────────────────────
   4. LISTE DES ÉMISSIONS
   GET /emissions
   Retourne : émissions avec tous leurs détails
──────────────────────────────────────────────────── */
export async function fetchEmissions() {
  console.log("🌿 Chargement des émissions détaillées...");
  return await requete("/emissions");

  /*
    Exemple de réponse attendue :
    [
      {
        "id"             : 1,
        "activite_id"    : 1,
        "co2_kg"         : 5616,
        "co2_tonnes"     : 5.616,
        "scope"          : "Scope 1",
        "facteur_utilise": 2.34
      },
      ...
    ]
  */
}


/* ──────────────────────────────────────────────────
   5. FACTEURS D'ÉMISSION GHG
   GET /emission-factors
   Retourne : les facteurs de conversion
   ex : 1 tonne de charbon = 2340 kg de CO₂
──────────────────────────────────────────────────── */
export async function fetchEmissionFactors() {
  console.log("📋 Chargement des facteurs d'émission...");
  return await requete("/emission-factors");

  /*
    Exemple de réponse attendue :
    [
      { "source": "Charbon",     "unite": "tonne", "facteur_co2": 2340 },
      { "source": "Gaz naturel", "unite": "m3",    "facteur_co2": 1.8  },
      { "source": "Electricite", "unite": "kWh",   "facteur_co2": 0.4  }
    ]
  */
}


/*
  ════════════════════════════════════════════════
  GUIDE D'UTILISATION dans un autre fichier JS

  Étape 1 — Importer les fonctions (en haut du fichier) :
    import { fetchStats, fetchActivities, addActivity } from './api.js';

  Étape 2 — Appeler dans une fonction async :
    async function chargerDashboard() {
      const stats = await fetchStats();

      if (stats === null) {
        // L'API ne répond pas, on garde les données affichées
        return;
      }

      // Mise à jour des KPI cards
      document.getElementById('kpi-total').textContent = stats.total_co2_tonnes;
    }

  Étape 3 — Mettre type="module" sur la balise <script> dans le HTML :
    <script type="module" src="js/dashboard.js"></script>
  ════════════════════════════════════════════════
*/
