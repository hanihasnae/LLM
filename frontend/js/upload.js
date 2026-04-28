/* ============================================================
   UPLOAD.JS — Gestion de l'upload PDF et affichage résultat
   ============================================================ */

const API = "http://localhost:8000";

/* ──────────────────────────────────────────────────
   1. INITIALISATION — Branche tous les événements
──────────────────────────────────────────────────── */
export function initUpload() {
  const zone   = document.getElementById('pdr-zone-upload');
  const input  = document.getElementById('pdr-fichier');

  if (!zone || !input) return;

  // ── Drag & Drop ──────────────────────────────────
  zone.addEventListener('dragover', function(e) // e = evenement
   {
    // Sans ça, le navigateur pourrait essayer d’ouvrir le fichier au lieu de permettre le dépôt.
    e.preventDefault();
    zone.style.borderColor = '#3fb950';
    zone.style.background  = 'rgba(63,185,80,0.05)';
  });

  zone.addEventListener('dragleave', function() {
    zone.style.borderColor = '';
    zone.style.background  = '';
  });

  zone.addEventListener('drop', function(e) {
    e.preventDefault();
    zone.style.borderColor = '';
    zone.style.background  = '';

    // dataTransfer.files contient la liste des fichiers déposés.
    const fichier = e.dataTransfer.files[0];
    if (fichier && fichier.name.endsWith('.pdf')) {
      traiterFichier(fichier);
    } else {
      afficherErreur('❌ Fichier non valide. Utilisez un PDF.');
    }
  });

  // ── Clic sur la zone ─────────────────────────────
  zone.addEventListener('click', function() {
    input.click();
  });

  // ── Sélection via explorateur ────────────────────
  input.addEventListener('change', function() {
    if (input.files[0]) {
      traiterFichier(input.files[0]);
    }
  });
}


/* ──────────────────────────────────────────────────
   2. TRAITEMENT DU FICHIER
──────────────────────────────────────────────────── */
async function traiterFichier(fichier) {
  console.log("📄 Fichier sélectionné :", fichier.name);

  // Affiche la barre de progression
  // Affiche la barre de progression avec le texte "Lecture du PDF..." et une progression à 20%.
  afficherProgression(true, "Lecture du PDF...", 20);

  try {
    // Crée un FormData (format pour envoyer des fichiers)
    const formData = new FormData();
    formData.append('fichier', fichier);

    // Simule progression pendant l'envoi
    afficherProgression(true, "Envoi vers l'API...", 40);

    // Envoie le PDF à FastAPI
    const reponse = await fetch(API + '/upload-pdf', {
      method: 'POST',
      body: formData
      // ⚠️ Ne pas mettre Content-Type — le navigateur le gère
    });

    afficherProgression(true, "Analyse LLM en cours...", 70);

    if (!reponse.ok) {
      const erreur = await reponse.json();
      throw new Error(erreur.detail || 'Erreur serveur');
    }

    const data = await reponse.json();
    console.log("✅ Données extraites :", data);

    afficherProgression(true, "Extraction terminée !", 100);

    // Attend 500ms puis affiche le résultat
    setTimeout(function() {
      afficherProgression(false);
      afficherResultat(data.donnees_extraites, fichier.name);
    }, 500); // 500 ms

  } catch (erreur) {
    console.error("❌ Erreur upload :", erreur);
    afficherProgression(false);
    afficherErreur('❌ Erreur : ' + erreur.message);
  }
}


/* ──────────────────────────────────────────────────
   3. AFFICHER LA BARRE DE PROGRESSION
──────────────────────────────────────────────────── */
function afficherProgression(visible, texte = '', pourcentage = 0) {
  const conteneur = document.getElementById('pdr-progression');
  const barre     = document.getElementById('pdr-barre');
  const statut    = document.querySelector('.pdr-statut');

  if (!conteneur) return;

  if (visible) {
    conteneur.style.display = 'block';
    if (barre)  barre.style.width  = pourcentage + '%';
    if (statut) statut.textContent = texte;
  } else {
    conteneur.style.display = 'none';
    if (barre) barre.style.width = '0%';
  }
}


/* ──────────────────────────────────────────────────
   4. AFFICHER LE RÉSULTAT DE L'EXTRACTION
──────────────────────────────────────────────────── */
function afficherResultat(donnees, nomFichier) {
  const zone = document.getElementById('pdr-resultat');
  if (!zone) return;

  // Couleur selon confiance
  const couleurConfiance = {
    'haute':   '#3fb950',
    'moyenne': '#f78166',
    'faible':  '#ff4560'
  };
  const couleur = couleurConfiance[donnees.confiance] || '#7a9e8a';

  // Calcul CO₂ estimé
  const facteurs = { electricity: 0.625, fuel: 3.24, gas: 2.02 };
  const facteur  = facteurs[donnees.type_energie] || 0;
  const co2_kg   = donnees.quantite ? (donnees.quantite * facteur).toFixed(2) : '—';

  zone.style.display = 'block';
  zone.innerHTML = `
    <!-- Header résultat -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <span class="badge badge-ok">✅ Extraction réussie</span>
      <span style="font-size:10px;color:${couleur};font-family:Consolas;">
        Confiance : ${donnees.confiance ?? '—'}
      </span>
    </div>

    <!-- Mini tableau des données extraites -->
    <table class="pdr-mini-tableau">
      <tr>
        <td>Fournisseur</td>
        <td>${donnees.fournisseur ?? '—'}</td>
      </tr>
      <tr>
        <td>Type</td>
        <td>${donnees.type_energie ?? '—'}</td>
      </tr>
      <tr>
        <td>Quantité</td>
        <td style="color:#3fb950;font-weight:600;">
          ${donnees.quantite ?? '—'} ${donnees.unite ?? ''}
        </td>
      </tr>
      <tr>
        <td>Date</td>
        <td>${donnees.date_facture ?? '—'}</td>
      </tr>
      <tr>
        <td>Montant</td>
        <td>${donnees.montant_dh ?? '—'} DH</td>
      </tr>
      <tr>
        <td>CO₂ estimé</td>
        <td style="color:#3fb950;font-weight:600;">${co2_kg} kg</td>
      </tr>
    </table>

    <!-- Boutons action -->
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button
        onclick="validerExtraction(${JSON.stringify(donnees).replace(/"/g, '&quot;')})"
        class="btn btn-primaire"
        style="flex:1;padding:8px;font-size:12px;">
        💾 Valider et enregistrer
      </button>
      <button
        onclick="annulerExtraction()"
        class="btn btn-contour"
        style="padding:8px 12px;font-size:12px;">
        ✕
      </button>
    </div>
  `;
}


/* ──────────────────────────────────────────────────
   5. VALIDER ET ENREGISTRER EN BASE
──────────────────────────────────────────────────── */
window.validerExtraction = async function(donnees) {
  const btn = event.target;
  btn.textContent = '⏳ Enregistrement...';
  btn.disabled = true;

  try {
    const reponse = await fetch(API + '/valider-extraction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(donnees)
    });

    const data = await reponse.json();

    if (!reponse.ok) {
      throw new Error(data.detail || 'Erreur serveur');
    }

    // Succès — affiche confirmation dans le chat IA
    ajouterMessageIA(
      `✅ Facture enregistrée ! ` +
      `${donnees.quantite} ${donnees.unite} → ` +
      `${data.co2_kg} kg CO₂ calculé. ` +
      `Dashboard mis à jour.`
    );

    // Cache le résultat
    document.getElementById('pdr-resultat').style.display = 'none';

    // Rafraîchit le dashboard
    if (typeof initDashboard === 'function') {
      setTimeout(initDashboard, 500);
    }

    console.log("✅ Enregistré :", data);

  } catch (erreur) {
    btn.textContent = '💾 Valider et enregistrer';
    btn.disabled = false;
    afficherErreur('❌ Erreur : ' + erreur.message);
  }
};


/* ──────────────────────────────────────────────────
   6. ANNULER L'EXTRACTION
──────────────────────────────────────────────────── */
window.annulerExtraction = function() {
  document.getElementById('pdr-resultat').style.display = 'none';
  document.getElementById('pdr-fichier').value = '';
};


/* ──────────────────────────────────────────────────
   7. AFFICHER UNE ERREUR
──────────────────────────────────────────────────── */
function afficherErreur(message) {
  const zone = document.getElementById('pdr-resultat');
  if (!zone) return;

  zone.style.display = 'block';
  zone.innerHTML = `
    <div style="
      background:rgba(255,69,96,0.08);
      border:1px solid rgba(255,69,96,0.2);
      border-radius:8px;
      padding:12px;
      font-size:12px;
      color:#ff4560;
    ">
      ${message}
      <div style="margin-top:8px;">
        <button onclick="annulerExtraction()" class="btn btn-contour" style="font-size:11px;">
          Réessayer
        </button>
      </div>
    </div>
  `;
}


/* ──────────────────────────────────────────────────
   8. AJOUTER MESSAGE AU CHAT IA
──────────────────────────────────────────────────── */
function ajouterMessageIA(texte) {
  const zone = document.getElementById('pdr-messages');
  if (!zone) return;

  const bulle = document.createElement('div');
  bulle.className   = 'pdr-msg pdr-msg--ia';
  bulle.textContent = texte;
  zone.appendChild(bulle);
  zone.scrollTop = zone.scrollHeight;
}