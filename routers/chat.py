# routers/chat.py
# Chat LLM connecté aux vraies données CarbonIQ

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os, requests as _req
from groq import Groq
from dotenv import load_dotenv
from database import get_connection
from cbam_chat_prompt import construire_prompt_chat, construire_system_chat, _SYSTEME_ACCUEIL
from cbam_engine import construire_contexte_cbam

load_dotenv()

# ── Configuration providers ───────────────────────────────────
GROQ_MODEL   = "llama-3.3-70b-versatile"
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")   # "groq" | "ollama"

router = APIRouter()


def groq_chat(messages: list, temperature: float = 0.3, max_tokens: int = 500) -> str:
    """Envoie une liste de messages à Groq (cloud) et retourne le texte généré."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()



def ollama_chat(messages: list, temperature: float = 0.3, max_tokens: int = 400) -> str:
    """Envoie une liste de messages à Ollama local et retourne le texte."""
    url = OLLAMA_URL.rstrip("/") + "/api/chat"
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": messages,
        "stream":   False,
        "options":  {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx":     2048,
        },
    }
    try:
        resp = _req.post(url, json=payload, timeout=480)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except _req.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Ollama inaccessible. Lancez : ollama serve")
    except _req.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail=f"Ollama dépasse 8 minutes sur {OLLAMA_MODEL}. Essayez : ollama pull qwen2.5:3b"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Ollama : {str(e)}")


def llm_chat(messages: list, temperature: float = 0.3, max_tokens: int = 500,
             provider: str = None) -> tuple[str, str]:
    """
    Dispatcher : envoie à Groq ou Ollama selon le provider demandé.
    Retourne (reponse_texte, label_modele).
    """
    p = (provider or LLM_PROVIDER).lower()
    if p == "ollama":
        return ollama_chat(messages, temperature, max_tokens=max_tokens), f"Ollama — {OLLAMA_MODEL}"
    return groq_chat(messages, temperature, max_tokens), f"Groq — {GROQ_MODEL}"


def get_provider_info(provider: str = None) -> dict:
    p = (provider or LLM_PROVIDER).lower()
    if p == "ollama":
        return {
            "provider": "ollama",
            "model":    OLLAMA_MODEL,
            "url":      OLLAMA_URL,
            "label":    f"Ollama — {OLLAMA_MODEL}",
            "local":    True,
        }
    return {
        "provider": "groq",
        "model":    GROQ_MODEL,
        "label":    f"Groq — {GROQ_MODEL}",
        "local":    False,
    }


# ── Détection des messages conversationnels simples ──────────────
_SALUTATIONS = frozenset({
    'bonjour', 'bonsoir', 'salut', 'hello', 'hi', 'coucou', 'hey',
    'merci', 'thanks', 'ok', 'bien', 'super', 'parfait', "d'accord",
    'compris', 'excellent', 'génial', 'bravo', 'chapeau',
    'au revoir', 'bye', 'à bientôt', 'bonne journée', 'bonne soirée', 'bonne nuit',
    'comment ça va', 'ça va', 'comment allez-vous',
})

def _est_message_simple(question: str) -> bool:
    """Retourne True si la question est une salutation/remerciement sans besoin de contexte DB."""
    q = question.lower().strip().rstrip('!.,?;:')
    if q in _SALUTATIONS:
        return True
    mots = q.split()
    if len(mots) <= 4 and any(mot in _SALUTATIONS for mot in mots):
        return True
    return False


def _compacter_system_ollama(system: str) -> str:
    """Réduit le message système pour les modèles locaux. Cible : ~800 chars."""
    systeme_court = (
        "Tu es Dr. CarbonIQ, expert CBAM. Réponds en 150 mots max, en français.\n"
        "Format: Ligne 1=[TAG] (DIAGNOSTIC/SIMULATION/ALERTE/PRESCRIPTION/RÉGLEMENTAIRE). "
        "Corps: analyse chiffrée. Dernière ligne: → Action: [quoi] d'ici [délai].\n\n"
    )
    mots_cles = (
        "TOTAL", "Scope 1", "Scope 2", "Scope 3", "tCO2e", "tCO₂",
        "Intensité", "intensite", "Benchmark", "benchmark",
        "taxe", "Taxe", "CBAM", "Secteur", "Production", "Route",
        "tendance", "ANOMALIE", "électricité", "fuel", "gaz",
    )
    lignes_cles = [
        l.strip() for l in system.split("\n")
        if l.strip() and any(kw.lower() in l.lower() for kw in mots_cles)
    ]
    return systeme_court + "DONNÉES:\n" + "\n".join(lignes_cles[:15])


def construire_messages(
    question:        str,
    historique:      list,
    simple:          bool  = False,
    contexte_db:     str   = "",
    contexte_cbam:   str   = "",
    profil:          dict  = None,
    contexte_avance: str   = "",
    provider:        str   = "groq",
) -> list:
    """Construit la liste de messages pour le LLM (système + historique + question)."""
    if simple:
        system_content = _SYSTEME_ACCUEIL
    else:
        system_content = construire_system_chat(contexte_db, contexte_cbam, profil, contexte_avance)

    # Ollama local : compacter le système pour économiser le contexte
    if provider == "ollama" and not simple:
        system_content = _compacter_system_ollama(system_content)

    # Garder les N derniers échanges selon le provider
    max_hist = 8 if provider == "ollama" else 14   # 4 ou 7 échanges
    hist = [
        {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
        for m in historique[-max_hist:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    return [{"role": "system", "content": system_content}] + hist + [{"role": "user", "content": question}]


class QuestionInput(BaseModel):
    question:   str
    provider:   Optional[str] = None   # "groq" | "ollama" | None → utilise LLM_PROVIDER
    historique: list           = []    # [{role, content}, ...] — derniers échanges


def get_contexte_entreprise() -> str:
    """Contexte enrichi : totaux, tendance MoM, anomalies, enjeu financier."""
    from datetime import datetime, date

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT SUM(e.co2_kg) as total_co2_kg, SUM(e.co2_kg)/1000 as total_co2_tonnes,
               COUNT(DISTINCT a.id) as nb_activites
        FROM activities a JOIN emissions e ON e.activity_id = a.id
        WHERE a.actif = true AND e.actif = true
    """)
    total = dict(cursor.fetchone())

    cursor.execute("""
        SELECT e.scope, SUM(e.co2_kg) as co2_kg
        FROM emissions e JOIN activities a ON a.id = e.activity_id
        WHERE a.actif = true AND e.actif = true
        GROUP BY e.scope ORDER BY e.scope
    """)
    scopes = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT a.source, SUM(a.quantity) as total_qty, a.unit, SUM(e.co2_kg) as co2_kg
        FROM activities a JOIN emissions e ON e.activity_id = a.id
        WHERE a.actif = true AND e.actif = true
        GROUP BY a.source, a.unit ORDER BY co2_kg DESC
    """)
    sources = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT TO_CHAR(a.date, 'YYYY-MM') as mois, SUM(e.co2_kg) as co2_kg
        FROM activities a JOIN emissions e ON e.activity_id = a.id
        WHERE a.actif = true AND e.actif = true
        GROUP BY mois ORDER BY mois DESC LIMIT 6
    """)
    par_mois = [dict(r) for r in cursor.fetchall()]

    # ── Scope 3 — chaîne de valeur ────────────────────────────────────────
    scope3_total_kg   = 0.0
    scope3_upstream   = 0.0
    scope3_downstream = 0.0
    scope3_par_cat    = {}
    scope3_nb         = 0
    try:
        cursor.execute("""
            SELECT direction, SUM(co2_kg) as total, COUNT(*) as nb
            FROM scope3_entries WHERE actif = true
            GROUP BY direction
        """)
        for row in cursor.fetchall():
            d = dict(row)
            val = float(d["total"] or 0)
            scope3_total_kg += val
            if d["direction"] == "upstream":
                scope3_upstream = val
                scope3_nb += int(d["nb"])
            else:
                scope3_downstream = val
                scope3_nb += int(d["nb"])

        cursor.execute("""
            SELECT category, category_name, SUM(co2_kg) as total
            FROM scope3_entries WHERE actif = true
            GROUP BY category, category_name ORDER BY total DESC LIMIT 4
        """)
        for row in cursor.fetchall():
            d = dict(row)
            scope3_par_cat[f"Cat{d['category']} {d['category_name']}"] = round(float(d["total"] or 0) / 1000, 3)
    except Exception:
        pass

    cursor.close()
    conn.close()

    scope1   = next((float(s["co2_kg"]) for s in scopes if s["scope"] == 1), 0)
    scope2   = next((float(s["co2_kg"]) for s in scopes if s["scope"] == 2), 0)
    scope3   = scope3_total_kg
    total_t  = round(float(total["total_co2_tonnes"] or 0), 2)
    s1_t     = round(scope1 / 1000, 2)
    s2_t     = round(scope2 / 1000, 2)
    s3_t     = round(scope3 / 1000, 2)
    total_complet_t = round(total_t + s3_t, 2)

    # ── Tendance mois en cours vs mois précédent (seulement si consécutifs) ──
    tendance_txt = "tendance: données insuffisantes"
    anomalie_txt = ""
    if len(par_mois) >= 2:
        from datetime import datetime as _dt
        try:
            d0 = _dt.strptime(par_mois[0]["mois"], "%Y-%m")
            d1 = _dt.strptime(par_mois[1]["mois"], "%Y-%m")
            diff_mois = (d0.year - d1.year) * 12 + (d0.month - d1.month)
            if diff_mois == 1:
                m0 = float(par_mois[0]["co2_kg"])
                m1 = float(par_mois[1]["co2_kg"])
                if m1 > 0:
                    delta_pct = round((m0 - m1) / m1 * 100, 1)
                    signe     = "+" if delta_pct >= 0 else ""
                    tendance_txt = f"tendance MoM: {signe}{delta_pct}% ({par_mois[0]['mois']} vs {par_mois[1]['mois']})"
                    if abs(delta_pct) > 20:
                        sens = "hausse" if delta_pct > 0 else "baisse"
                        anomalie_txt = f"⚠ ANOMALIE: {sens} de {abs(delta_pct)}% ce mois — investigation requise"
            else:
                tendance_txt = (
                    f"données non consécutives ({par_mois[0]['mois']} et {par_mois[1]['mois']}, "
                    f"écart {diff_mois} mois) — comparaison MoM non applicable"
                )
        except Exception:
            pass

    # ── Jours avant prochaine déclaration CBAM trimestrielle ──────────────
    aujourd_hui = date.today()
    trimestres  = [date(aujourd_hui.year, 1, 31), date(aujourd_hui.year, 4, 30),
                   date(aujourd_hui.year, 7, 31), date(aujourd_hui.year, 10, 31)]
    prochaine   = next((d for d in trimestres if d >= aujourd_hui), date(aujourd_hui.year + 1, 1, 31))
    jours_decl  = (prochaine - aujourd_hui).days

    # ── Top sources Scope 1+2 ─────────────────────────────────────────────
    top3_txt = " | ".join(
        f"{s['source']}={round(float(s['co2_kg'])/1000, 2)}t"
        for s in sources[:3]
    )

    # ── Proportion Scope 3 ────────────────────────────────────────────────
    pct_s3 = round(s3_t / total_complet_t * 100, 1) if total_complet_t > 0 else 0

    lignes = [
        "=== BILAN COMPLET SCOPE 1+2+3 ===",
        f"Scope 1 (direct):      {s1_t} tCO2e",
        f"Scope 2 (électricité): {s2_t} tCO2e",
        f"Scope 3 (chaîne val.): {s3_t} tCO2e  [{scope3_nb} entrées | upstream={round(scope3_upstream/1000,3)}t | downstream={round(scope3_downstream/1000,3)}t]",
        f"TOTAL S1+S2+S3:        {total_complet_t} tCO2e  (S3 = {pct_s3}% de l'empreinte totale)",
        f"",
        f"=== SCOPE 1+2 DÉTAIL ===",
        f"Activités enregistrées: {total['nb_activites']}",
        f"Sources principales: {top3_txt or 'aucune'}",
        f"Évolution mensuelle (S1+S2): " + " → ".join(
            f"{m['mois']}={round(float(m['co2_kg'])/1000,2)}t" for m in par_mois[:4]
        ),
        tendance_txt,
        f"",
        f"=== SCOPE 3 DÉTAIL ===",
    ]

    if scope3_par_cat:
        for cat, val in scope3_par_cat.items():
            lignes.append(f"  {cat}: {val} tCO2e")
    else:
        lignes.append("  Aucune donnée Scope 3 enregistrée")

    lignes += [
        f"",
        f"=== DÉCLARATION CBAM ===",
        f"Prochaine déclaration: {prochaine.strftime('%d/%m/%Y')} (dans {jours_decl} jours)",
    ]
    if anomalie_txt:
        lignes.append(anomalie_txt)

    return "\n".join(lignes)


class QuestionCBAMInput(BaseModel):
    question:          str
    production_tonnes: float = 0   # optionnel — si fourni, active le calcul CBAM complet
    cn_code:           str   = ""  # optionnel — code NC du produit
    mot_cle:           str   = ""  # optionnel — ex: "steel", "aluminium"


def _get_profil_db():
    """Lit le profil entreprise depuis la DB."""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM company_profile ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        cursor.close(); conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _get_colonne_from_profil(profil: dict) -> str:
    if not profil:
        return None
    _SECTEUR_CBAM_KEY = {
        "Acier/Fer": "Iron & Steel", "Aluminium": "Aluminium",
        "Ciment": "Cement",          "Engrais":   "Fertilisers",
        "Hydrogène": "Hydrogen",
    }
    from cbam_reference_complete import get_colonne_obligatoire
    cbam_key = _SECTEUR_CBAM_KEY.get(profil.get("secteur", ""), "")
    return get_colonne_obligatoire(cbam_key) if cbam_key else None


def _get_total_co2(colonne: str = None) -> float:
    """
    Retourne le CO₂ actif filtré par scope selon la colonne CBAM :
    - Column A (Steel, Alu, H₂) : Scope 1 seulement (émissions directes)
    - Column B (Cement, Engrais) : Scope 1 + Scope 2 (total)
    - None / inconnu            : total (Scope 1 + 2) par défaut
    """
    conn   = get_connection()
    cursor = conn.cursor()
    if colonne == 'A':
        cursor.execute("""
            SELECT COALESCE(SUM(e.co2_kg), 0) as total
            FROM emissions e
            JOIN activities a ON a.id = e.activity_id
            WHERE a.actif = true AND e.actif = true AND e.scope = 1
        """)
    else:
        cursor.execute("""
            SELECT COALESCE(SUM(e.co2_kg), 0) as total
            FROM emissions e
            JOIN activities a ON a.id = e.activity_id
            WHERE a.actif = true AND e.actif = true
        """)
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return float(row["total"])


@router.get("/chat/info")
def chat_info():
    """Retourne le provider LLM actif et ses informations."""
    return get_provider_info()


@router.post("/chat")
def chat(data: QuestionInput):
    """Chat LLM multi-turn — lit le profil entreprise automatiquement."""

    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question vide")

    provider = (data.provider or LLM_PROVIDER).lower()
    simple   = _est_message_simple(data.question)

    contexte_db     = ""
    contexte_cbam   = ""
    contexte_avance = ""
    profil          = None

    # Pour les salutations/remerciements : pas de contexte DB nécessaire
    if not simple:
        contexte_db = get_contexte_entreprise()
        profil      = _get_profil_db()

        if profil and profil.get("production_annuelle_tonnes"):
            _SECTEUR_MOT_CLE  = {
                "Acier/Fer": "steel",    "Aluminium": "aluminium",
                "Ciment": "cement",      "Engrais": "fertiliser",
                "Hydrogène": "hydrogen"
            }
            _SECTEUR_CBAM_KEY = {
                "Acier/Fer": "Iron & Steel", "Aluminium": "Aluminium",
                "Ciment": "Cement",          "Engrais": "Fertilisers",
                "Hydrogène": "Hydrogen"
            }
            mot_cle     = _SECTEUR_MOT_CLE.get(profil.get("secteur", ""), "")
            secteur_key = _SECTEUR_CBAM_KEY.get(profil.get("secteur", ""), "")
            from cbam_reference_complete import get_colonne_obligatoire
            colonne_cbam = get_colonne_obligatoire(secteur_key) if secteur_key else None

            contexte_cbam = construire_contexte_cbam(
                total_co2_kg      = _get_total_co2(colonne_cbam),
                production_tonnes = profil["production_annuelle_tonnes"],
                cn_code           = profil.get("cn_code") or None,
                mot_cle           = mot_cle or None,
                secteur           = secteur_key or None,
                route             = profil.get("route_production") or None,
            )

            prod_t = profil["production_annuelle_tonnes"]
            co2_t  = _get_total_co2(_get_colonne_from_profil(profil)) / 1000
            if prod_t > 0 and co2_t > 0:
                intensite  = round(co2_t / prod_t, 4)
                enjeu_taxe = round(co2_t * 76.50, 0)
                contexte_avance = (
                    f"Intensité actuelle: {intensite} tCO2e/tonne\n"
                    f"Enjeu financier approximatif: {enjeu_taxe:,.0f} €\n"
                    f"Réduction 10% fuel ≈ économie {round(co2_t * 0.1 * 0.7 * 76.50, 0):,.0f} €"
                )

    messages = construire_messages(
        question        = data.question,
        historique      = data.historique,
        simple          = simple,
        contexte_db     = contexte_db,
        contexte_cbam   = contexte_cbam,
        profil          = profil,
        contexte_avance = contexte_avance,
        provider        = provider,
    )

    reponse, modele_label = llm_chat(messages, temperature=0.3, max_tokens=600, provider=provider)
    return {
        "question":         data.question,
        "reponse":          reponse,
        "cbam_active":      bool(contexte_cbam),
        "profil_configure": profil is not None,
        "modele":           modele_label,
        "provider":         provider,
        "simple":           simple,
    }


@router.post("/chat/cbam")
def chat_cbam(data: QuestionCBAMInput):
    """Chat LLM avec analyse CBAM complète (nécessite production_tonnes)."""

    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question vide")

    contexte_db = get_contexte_entreprise()

    # Extrait le total CO₂ depuis le contexte DB
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(e.co2_kg) as total
        FROM emissions e
        JOIN activities a ON a.id = e.activity_id
        WHERE a.actif = true AND e.actif = true
    """)
    row           = cursor.fetchone()
    cursor.close(); conn.close()
    total_co2_kg  = float(row["total"] or 0)

    contexte_cbam = ""
    if data.production_tonnes > 0:
        contexte_cbam = construire_contexte_cbam(
            total_co2_kg      = total_co2_kg,
            production_tonnes = data.production_tonnes,
            cn_code           = data.cn_code   or None,
            mot_cle           = data.mot_cle   or None
        )

    provider = (data.provider or LLM_PROVIDER).lower()
    messages = construire_messages(
        question    = data.question,
        historique  = [],
        simple      = False,
        contexte_db = contexte_db,
        contexte_cbam = contexte_cbam,
        provider    = provider,
    )

    reponse, modele_label = llm_chat(messages, temperature=0.3, max_tokens=600, provider=provider)
    return {
        "question":          data.question,
        "reponse":           reponse,
        "cbam_active":       data.production_tonnes > 0,
        "total_co2_kg":      round(total_co2_kg, 2),
        "production_tonnes": data.production_tonnes,
        "modele":            modele_label,
        "provider":          provider,
    }


@router.get("/chat/suggestions")
def get_suggestions():
    """Retourne des suggestions de questions basées sur les données"""

    contexte  = get_contexte_entreprise()

    # Suggestions fixes à haute valeur ajoutée — ce que les graphiques ne montrent pas
    return {
        "suggestions": [
            "Simuler réduction 20% fuel → impact sur ma taxe CBAM ?",
            "Pourquoi mes émissions ont-elles évolué ce mois ?",
            "Quelle est mon action prioritaire pour réduire mon risque CBAM ?",
            "Ma trajectoire actuelle me rend-elle conforme pour la prochaine déclaration ?",
        ]
    }