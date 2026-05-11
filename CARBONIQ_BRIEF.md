# CarbonIQ — Brief Complet pour Consultation IA
> Fichier de contexte pour obtenir des recommandations d'optimisation et de roadmap.  
> Stack : **FastAPI + PostgreSQL + Groq LLM + ReportLab PDF**  
> Contexte : Plateforme MRV CBAM pour exportateurs marocains vers l'UE.  
> Date snapshot : 2026-05-10

---

## 1. Ce qui est entièrement fonctionnel

### Backend FastAPI (`main.py` + 9 routers)

| Router | Préfixe | Ce qu'il fait |
|---|---|---|
| `data.py` | `/activities` | CRUD consommations (élec/fuel/gaz) + calcul CO2 automatique via facteurs GHG |
| `company.py` | `/company` | Profil CBAM entreprise (1 ligne unique en DB) |
| `cbam.py` | `/cbam` | Conformité CBAM via `cbam_engine.py` + benchmarks Excel EU 2025/2620 |
| `chat.py` | `/chat` | Chat LLM Dr. CarbonIQ (Groq llama-3.3-70b) avec RAG temps réel DB |
| `pdf.py` | `/upload-pdf` | Upload factures PDF → extraction LLM (Mistral/Groq) |
| `report.py` | `/generate-report` | Rapport PDF CBAM 8 pages (ReportLab) avec DVs officiels intégrés |
| `tracabilite.py` | `/activities/{id}/...` | Soft delete + journal modifications ISO 14064 |
| `scope3.py` | `/scope3` | CRUD émissions chaîne de valeur (6 catégories GHG Protocol) |
| `erp.py` | — | Simulation import données ERP en masse |

### Base de données PostgreSQL — 8 tables

| Table | Rôle |
|---|---|
| `activities` | Consommations avec soft-delete (`actif`), `methode_saisie`, `source_document` |
| `emissions` | CO2 calculé par activité (Scope 1/2), `actif` |
| `emission_factors` | Facteurs GHG Maroc : élec=0.625, fuel=3.24, gaz=2.02 kg CO2/unité |
| `company_profile` | Profil CBAM (secteur, cn_code, production_tonnes, route) — 1 ligne |
| `audit_log` | Traçabilité ISO 14064 — each modif génère une entrée |
| `journal_modifications` | Détail champ-par-champ des modifications (ancienne/nouvelle val, raison) |
| `scope3_entries` | Émissions Scope 3 avec 13 champs (transport, fournisseur, qualité donnée) |
| `journal_scope3` | Traçabilité soft-delete Scope 3 |

### Moteur CBAM — 3 fichiers métier

- **`cbam_engine.py`** : calcul conformité via `benchmarks_cbam.xlsx` (UE 2025/2620), `PRIX_CARBONE_EU = 76.50 €`, `calculer_conformite()`, `construire_contexte_cbam()`
- **`cbam_reference_complete.py`** : dictionnaire Python pur — 5 secteurs, règle Column A/B
- **`cbam_dv_loader_lite.py`** : DVs officiels `DVs as adopted_v20260204.xlsx` — 120 pays, mark-ups 2026→2028, singleton avec cache mémoire
- **`routers/cbam_conformite.py`** : module de calcul pur (pas de router) — `calculer_conformite_cbam()` avec Free Allocation 2026-2030, déduction Art.9

### LLM — Dr. CarbonIQ (`routers/chat.py` + `cbam_chat_prompt.py`)

**Ce que fait le LLM :**
1. Récupère le contexte temps réel de la DB (Scope 1+2+3, tendance MoM, anomalies >20%)
2. Lit le profil entreprise automatiquement pour activer l'analyse CBAM (Column A ou B)
3. Calcule la conformité CBAM en direct avant chaque réponse
4. Construit un prompt structuré (système + RAG + données) envoyé à Groq
5. Répond avec un tag forcé : `[DIAGNOSTIC]` / `[SIMULATION]` / `[ALERTE]` / `[PRESCRIPTION]` / `[RÉGLEMENTAIRE]`
6. Chiffre toutes ses recommandations avec les vraies données DB (€, tCO2, %)
7. Intègre le Scope 3 dans le bilan total et signale si S3 > S1+S2 (levier ignoré)
8. Calcule les jours avant prochaine déclaration CBAM trimestrielle
9. Génère 4 recommandations personnalisées dans le rapport PDF (ReportLab page 7)

**Endpoints LLM :**
- `POST /chat` — question simple, enrichi auto avec profil DB
- `POST /chat/cbam` — analyse CBAM avec `production_tonnes` + `cn_code` custom
- `GET /chat/suggestions` — 4 questions prédéfinies à haute valeur ajoutée

### Scope 3 (`routers/scope3.py`)
- 6 catégories GHG Protocol : Cat 1 (matières), Cat 3 (énergie amont), Cat 4 (transport entrant), Cat 5 (déchets), Cat 9 (transport sortant), Cat 12 (fin de vie)
- 27 facteurs d'émission hardcodés (acier, aluminium, ciment, transport, déchets...)
- Calcul automatique t.km pour transport (poids × distance)
- `GET /scope3/summary` — upstream/downstream totaux + par catégorie + qualité données
- Soft delete ISO 14064 + `journal_scope3`

### Rapport PDF (`routers/report.py`)
8 sections avec ReportLab :
1. Couverture + références réglementaires
2. Identification installation + Column A/B
3. Goods Imported — Section 2 CBAM Art.35
4. Bilan MRV (graphiques pie + bar, tableau par source, évolution mensuelle)
5. Conformité CBAM (jauge visuelle, KPIs, taxe, Free Allocation, **DVs officiels**)
6. Données Monitoring (30 dernières activités + journal ISO 14064)
7. Recommandations LLM (Groq — 4 recommandations personnalisées)
8. Déclaration conformité + signature + vérification tierce
9. Annexes (facteurs GHG, benchmarks secteur, glossaire)

### Frontend (`frontend/index.html`)
- Thème dark/light
- Tableau de bord avec graphiques
- Interface chat Dr. CarbonIQ
- Page conformité CBAM
- Servi statiquement via `/frontend/`

### Scripts standalone
- `iot_simulator.py` — 4 capteurs IoT simulés, POST `/activities` toutes les 10-60s
- `erp_simulator.py` — simulation import ERP en masse

---

## 2. Architecture des données — Points importants

```
Scope 1 (fuel, gaz)     ──┐
Scope 2 (électricité)   ──┤─→ activities + emissions tables → /summary
                          │
Scope 3 (chaîne valeur) ──┘─→ scope3_entries table → /scope3/summary

company_profile (1 ligne) ──→ détermine Column A/B pour CBAM
                          ──→ enrichit automatiquement le contexte LLM

PRIX_CARBONE_EU = 76.50 €/tCO2 (hardcodé dans cbam_engine.py ET cbam_conformite.py)
FREE_ALLOCATION 2026-2030 (hardcodé dans cbam_conformite.py)
```

---

## 3. Ce qui est absent ou incomplet — Points bloquants

### Critique (impact fonctionnel direct)

1. **Pas d'authentification** — `allow_origins=["*"]` en CORS, aucun JWT/session. Toute personne avec l'URL accède à tout.
2. **`company_profile` = 1 ligne unique** — `ORDER BY id LIMIT 1` dans tous les routers. Multi-entreprise impossible.
3. **Colonne `statut_verification` absente de la DB** — utilisée dans le rapport PDF (page 7) mais non créée dans `create_tables()`. Crash potentiel ou `None` silencieux.
4. **Connexions DB non poolées** — chaque requête API ouvre + ferme une connexion `psycopg2`. Pas de `connection pool`. Scalabilité limitée.
5. **Facteurs Scope 3 hardcodés** dans `routers/scope3.py` (dict Python) — non éditables depuis l'API, non versionnés, pas de mise à jour possible sans redéploiement.
6. **`PRIX_CARBONE_EU = 76.50` dupliqué** dans `cbam_engine.py` ET `cbam_conformite.py` — deux sources de vérité.

### Fonctionnel mais fragile

7. **Lecture Excel au démarrage sans fallback** — si `benchmarks_cbam.xlsx` ou `DVs as adopted_v20260204.xlsx` est absent/corrompu, le serveur démarre mais les endpoints CBAM échouent silencieusement.
8. **Max 500 tokens LLM** — répenses tronquées sur questions complexes (`max_tokens=500` dans `groq_chat()`).
9. **Pas de gestion d'erreur Groq** — si l'API Groq est indisponible, le chat retourne HTTP 500 sans retry ni fallback.
10. **Tendance MoM fragile** — si les activités ne sont pas consécutives (gap de mois), le calcul affiche "données non consécutives" sans suggestion.

### Absent (fonctionnalités mentionnées dans CLAUDE.md mais non implémentées)

11. **Export XML CBAM officiel** — format requis pour soumission douanes UE (non commencé).
12. **Dashboard temps réel WebSockets** pour données IoT (non commencé).
13. **Mise à jour automatique prix EU ETS** (actuellement hardcodé).
14. **Support multi-pays** pour DVs — le loader supporte 120 pays mais le profil est fixé sur Maroc (`pays_origine="MA"` par défaut).

---

## 4. Ce qui doit être optimisé

### Performance
- **Connection pooling** : remplacer `psycopg2.connect()` direct par `psycopg2.pool.ThreadedConnectionPool` ou migrer vers `asyncpg` + `databases` pour du vrai async.
- **Cache DVs** : le singleton `DVLoader` est bien, mais il ne survit pas à un restart. Envisager Redis pour cache persistant entre restarts.
- **Requêtes N+1** dans `report.py` : plusieurs `get_connection()` séquentiels — regrouper en une seule connexion par request.

### Maintenabilité
- **Variables d'environnement manquantes** : `PRIX_CARBONE_EU`, `FREE_ALLOCATION` devraient être dans `.env` ou une table DB `cbam_parameters`.
- **Facteurs Scope 3** : déplacer de `scope3.py` vers une table `scope3_factors` en DB avec CRUD.
- **Modèles Pydantic** centralisés : `models.py` est vide, mais chaque router redéfinit ses propres `BaseModel`. Les factoriser.

### Qualité LLM
- **Historique de conversation absent** — chaque `POST /chat` est stateless. Le LLM ne se souvient pas des échanges précédents. Implémenter `conversation_history` en mémoire ou DB.
- **Prompt trop long** : le `contexte_db` peut dépasser 1000 tokens si beaucoup de données mensuelles. Ajouter une troncature intelligente.
- **Pas de streaming** — la réponse LLM est attendue entièrement avant d'être retournée. `StreamingResponse` améliorerait l'UX.

### Sécurité
- **Injection SQL potentielle** : `entry: dict` dans `scope3.py` — les valeurs ne sont pas validées (pas de Pydantic model). Un `entry.get("quantity")` non typé peut provoquer des erreurs.
- **CORS `allow_origins=["*"]`** à restreindre en production.
- **Clés API dans `.env`** mais pas de validation au démarrage (si `GROQ_API_KEY` est vide, crash à la première requête chat).

---

## 5. Roadmap suggérée — Par priorité

### Phase 1 — Stabilité (1-2 semaines)
- [ ] **Créer `statut_verification` en DB** dans `create_tables()` — ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS
- [ ] **Unifier `PRIX_CARBONE_EU`** — une seule constante importée dans `cbam_engine.py`, utilisée par `cbam_conformite.py`
- [ ] **Ajouter Pydantic models** pour `scope3.py` (remplacer `entry: dict` par une vraie `BaseModel`)
- [ ] **Valider clés API au démarrage** dans `startup()` — warning si GROQ_API_KEY manquant
- [ ] **Fallback Excel CBAM** — try/except au chargement des fichiers Excel avec message d'erreur clair

### Phase 2 — Fonctionnalités clés (2-4 semaines)
- [ ] **Historique conversation LLM** — table `chat_history(session_id, role, content, created_at)` + les 5 derniers messages injectés dans le prompt
- [ ] **Streaming LLM** — `StreamingResponse` sur `POST /chat` avec SSE
- [ ] **Connection pool PostgreSQL** — `ThreadedConnectionPool(minconn=2, maxconn=10)`
- [ ] **Table `cbam_parameters`** en DB — `prix_carbone_eu`, `free_allocation_*`, modifiables via API

### Phase 3 — Évolutivité (1-2 mois)
- [ ] **Authentification JWT** — `python-jose` + `passlib`, table `users`, token Bearer
- [ ] **Multi-entreprise** — ajouter `user_id` dans `company_profile`, `activities`, `scope3_entries`
- [ ] **Export XML CBAM** — format officiel EU douanes (champ `quantite_importee` déjà présent dans `RapportRequest`)
- [ ] **WebSockets IoT** — endpoint `WS /ws/activities` pour dashboard temps réel

### Phase 4 — Intelligence (2-3 mois)
- [ ] **Alertes automatiques** — job Celery/APScheduler qui détecte anomalies MoM et envoie email/webhook
- [ ] **Prévision CO2** — régression linéaire sur 6 derniers mois pour estimer fin d'année vs benchmark
- [ ] **Scope 3 enrichi** — facteurs depuis base ECOINVENT ou GHG Protocol officiel (remplace dict hardcodé)
- [ ] **Mise à jour prix EU ETS** — scraping hebdomadaire `api.ember-climate.org` ou similar

---

## 6. Variables d'environnement requises

```env
# Obligatoires
DATABASE_URL=postgresql://user:pass@localhost:5432/carboniq
GROQ_API_KEY=gsk_...

# Optionnelles (actuellement hardcodées dans le code)
MISTRAL_API_KEY=...          # Upload PDF (routers/pdf.py)
PRIX_CARBONE_EU=76.50        # À externaliser depuis cbam_engine.py
```

---

## 7. Questions à poser à Claude pour continuer

1. **"Comment implémenter l'historique de conversation dans `/chat` sans ORM, juste psycopg2 ?"**
2. **"Montre-moi comment faire du streaming LLM avec Groq + FastAPI StreamingResponse + SSE côté JS."**
3. **"Comment ajouter JWT à ce projet FastAPI sans casser les endpoints existants ?"**
4. **"Rends le Scope 3 dynamique : créer une table `scope3_factors` avec CRUD et migrer depuis le dict hardcodé."**
5. **"Génère le XML CBAM officiel (format EU) depuis les données du rapport PDF existant."**
6. **"Comment faire du connection pooling psycopg2 dans FastAPI sans passer à SQLAlchemy ?"**

---

## 8. Références réglementaires du projet

| Règlement | Objet |
|---|---|
| UE 2023/956 | CBAM — mécanisme d'ajustement carbone aux frontières |
| UE 2025/2620 | Benchmarks d'émissions par secteur (Excel `benchmarks_cbam.xlsx`) |
| UE 2025/2621 | Default Values officiels par pays (Excel `DVs as adopted_v20260204.xlsx`) |
| UE 2025/2546 | Vérification tierce indépendante (page 8 du rapport PDF) |
| GHG Protocol Rev. 2024 | Comptabilité Scope 1/2/3 |
| ISO 14064 | Quantification et rapport GES (soft delete + journal traçabilité) |

---

*CarbonIQ v1.0 | Snapshot 2026-05-10 | Hasna*
