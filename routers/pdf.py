# routers/pdf.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pdfplumber
import os
import json
import tempfile
from groq import Groq
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# ── Clients LLM ───────────────────────────────────────
GROQ_KEY    = os.getenv("GROQ_API_KEY")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")

groq_client    = Groq(api_key=GROQ_KEY)              if GROQ_KEY    else None
mistral_client = Mistral(api_key=MISTRAL_KEY)         if MISTRAL_KEY else None

print(f"[LLM] Groq    : {'OK' if groq_client    else 'cle manquante'}")
print(f"[LLM] Mistral : {'OK' if mistral_client else 'cle manquante'}")


def extraire_texte_pdf(fichier_bytes: bytes) -> str:
    """Extrait le texte d'un PDF"""
    texte_complet = ""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(fichier_bytes)
        tmp_path = tmp.name

    try:
        with pdfplumber.open(tmp_path) as pdf:
            print(f"📄 PDF ouvert : {len(pdf.pages)} page(s)")
            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                print(f"   Page {i+1} : {len(texte) if texte else 0} caractères")
                if texte:
                    texte_complet += texte + "\n"
    except Exception as e:
        print(f"❌ Erreur pdfplumber : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture PDF : {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

    return texte_complet


def calculer_confiance(donnees: dict) -> str:
    champs = ["fournisseur", "quantite", "date_facture", "montant_dh"]
    remplis = sum(1 for c in champs if donnees.get(c) is not None)
    if remplis == 4: return "haute"
    if remplis >= 2: return "moyenne"
    return "faible"


def analyser_avec_llm(texte: str) -> dict:
    """Analyse le texte avec Groq LLM — supporte electricity, fuel, gas"""

    prompt = f"""Tu es un expert en analyse de factures énergétiques.
Analyse cette facture et extrait les informations demandées.

TEXTE DE LA FACTURE :
{texte[:3000]}

═══ ÉTAPE 1 : identifie le type d'énergie ═══

Cherche dans le texte :
- Électricité → "kWh", "électricité", "ONEE", "Office National de l'Electricité", "Facture d'électricité"
- Fuel/Diesel → "gasoil", "diesel", "fuel", "fioul", "carburant", "Gasoil excelium", "Quantité(L)", "litres", "Total Maroc", "Shell", "Afriquia"
- Gaz naturel → "gaz naturel", "m3", "mètres cubes", "BTU", "Afriquia Gaz", "Gazco", "Gazprom"

Définis en conséquence :
  électricité → type_energie = "electricity", unite = "kWh"
  fuel/diesel → type_energie = "fuel",        unite = "litres"
  gaz naturel → type_energie = "gas",         unite = "m3"

═══ ÉTAPE 2 : extrais les champs ═══

[fournisseur]
Nom du fournisseur en haut de la facture.
Exemples : ONEE, Total Maroc, Shell, Afriquia, Gazco, Vivo Energy, etc.

[quantite]
Quantité d'énergie livrée ou consommée.
- Électricité : kWh. Cherche "Quantité (kWh)", "Consommation".
  ⚠️ Additionne les tranches si nécessaire (ex: 90 + 30 = 120 kWh).
- Fuel : litres. Cherche "Quantité(L)", "Quantité (L)", "Volume", "Qté".
  ⚠️ "929,36" avec virgule = 929.36 (virgule = décimale).
  ⚠️ "1.200" avec point = 1200 (point = séparateur milliers).
- Gaz : m³. Cherche "Volume (m3)", "Consommation (m3)", "Qté m3".

[date_facture]
Date d'émission de la facture au format YYYY-MM-DD.
Cherche "Date :", "Facturé le", "Date de facturation", "Date facture".
⚠️ ONEE : utilise le champ "Date" de l'entête uniquement.
   Ignore "du JJ.MM.AAAA au JJ.MM.AAAA" (période conso).
Conversions :
  "16.08.2023"  → "2023-08-16"
  "26/06/2020"  → "2020-06-26"
  "22/01/2026"  → "2026-01-22"
  "22 Jan 2026" → "2026-01-22"

[montant_dh]
Montant total TTC final à payer.
Cherche "Total", "Total facture", "Total à régler", "Net à payer",
        "Montant TTC", "Prix total", "Total TTC", "Tota".
⚠️ Point séparateur milliers : "500.000" = 500000
⚠️ Virgule décimale          : "133,26"  = 133.26
⚠️ Retourne toujours un nombre décimal.
Exemples : "500.000 Fcfa" → 500000 / "133,26 DH" → 133.26 / "45 000 MAD" → 45000

[numero_facture]
Numéro ou référence de la facture. null si absent.

[confiance]
- "haute"   : tous les champs trouvés avec certitude
- "moyenne" : 1 ou 2 champs manquants ou incertains
- "faible"  : beaucoup de champs manquants

═══ ÉTAPE 3 : retourne le JSON ═══

Réponds UNIQUEMENT avec ce JSON exact, rien d'autre,
pas de texte avant, pas de texte après, pas de ```json :
{{
  "fournisseur": null,
  "type_energie": null,
  "quantite": null,
  "unite": null,
  "periode": null,
  "date_facture": null,
  "montant_dh": null,
  "numero_facture": null,
  "confiance": null
}}"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400
        )

        texte_reponse = response.choices[0].message.content.strip()
        print(f"🤖 Réponse LLM brute : {texte_reponse}")

        # Nettoie si le LLM a ajouté du texte autour du JSON
        debut = texte_reponse.find('{')
        fin   = texte_reponse.rfind('}') + 1
        if debut != -1 and fin > debut:
            texte_reponse = texte_reponse[debut:fin]

        donnees = normaliser(json.loads(texte_reponse))
        print(f"✅ Groq données : {donnees}")
        return donnees

    except json.JSONDecodeError as e:
        print(f"❌ JSON invalide : {texte_reponse}")
        return {
            "fournisseur":    None,
            "type_energie":   None,
            "quantite":       None,
            "unite":          None,
            "date_facture":   None,
            "montant_dh":     None,
            "numero_facture": None,
            "confiance":      "faible",
            "note":           "Extraction échouée - vérification manuelle requise"
        }

    except Exception as e:
        print(f"❌ Erreur Groq : {e}")
        return None   # signale l'échec pour déclencher le fallback Mistral


def normaliser(donnees: dict) -> dict:
    """Corrections post-extraction communes à Groq et Mistral."""
    if donnees.get("type_energie"):
        t = donnees["type_energie"].lower().strip()
        if t in ["electricite", "électricité", "electric"]:      t = "electricity"
        elif t in ["diesel", "gasoil", "carburant", "fioul"]:    t = "fuel"
        elif t in ["gaz", "gas naturel", "gaz naturel"]:         t = "gas"
        donnees["type_energie"] = t

    unites = {"electricity": "kWh", "fuel": "litres", "gas": "m3"}
    if donnees.get("type_energie") in unites:
        donnees["unite"] = unites[donnees["type_energie"]]

    for champ in ["quantite", "montant_dh"]:
        if donnees.get(champ) is not None:
            try:
                donnees[champ] = float(str(donnees[champ]).replace(",", ".").replace(" ", ""))
            except:
                donnees[champ] = None

    donnees["confiance"] = calculer_confiance(donnees)
    return donnees


def analyser_avec_mistral(texte: str) -> dict | None:
    """Fallback Mistral si Groq échoue ou retourne confiance faible."""
    if not mistral_client:
        print("⚠️ Mistral non configuré — pas de fallback disponible")
        return None

    print("🔄 Fallback → Mistral...")

    # Même prompt que Groq
    prompt = analyser_avec_llm.__doc_prompt__ if hasattr(analyser_avec_llm, '__doc_prompt__') else None

    # Reconstruit le prompt directement
    prompt = f"""Tu es un expert en analyse de factures énergétiques.
Analyse cette facture et extrait les informations demandées.

TEXTE DE LA FACTURE :
{texte[:3000]}

═══ ÉTAPE 1 : identifie le type d'énergie ═══
- Électricité → "kWh", "électricité", "ONEE" → type_energie = "electricity", unite = "kWh"
- Fuel/Diesel → "gasoil", "diesel", "litres", "carburant" → type_energie = "fuel", unite = "litres"
- Gaz naturel → "gaz naturel", "m3" → type_energie = "gas", unite = "m3"

═══ ÉTAPE 2 : extrais les champs ═══
[fournisseur] Nom du fournisseur.
[quantite] Quantité consommée (kWh, litres ou m3). Virgule = décimale. Point = milliers.
[date_facture] Date d'émission YYYY-MM-DD. Pour ONEE : champ "Date" uniquement, ignore "du ... au ...".
[montant_dh] Montant TTC total. "500.000"=500000, "133,26"=133.26.
[numero_facture] Numéro de facture, null si absent.

Réponds UNIQUEMENT avec ce JSON :
{{
  "fournisseur": null,
  "type_energie": null,
  "quantite": null,
  "unite": null,
  "date_facture": null,
  "montant_dh": null,
  "numero_facture": null
}}"""

    try:
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400
        )
        texte_reponse = response.choices[0].message.content.strip()
        print(f"🤖 Mistral brut : {texte_reponse}")

        debut = texte_reponse.find('{')
        fin   = texte_reponse.rfind('}') + 1
        if debut != -1 and fin > debut:
            texte_reponse = texte_reponse[debut:fin]

        donnees = json.loads(texte_reponse)
        donnees = normaliser(donnees)
        donnees["_source"] = "mistral"
        print(f"✅ Mistral confiance : {donnees['confiance']}")
        return donnees

    except Exception as e:
        print(f"❌ Erreur Mistral : {e}")
        return None


def analyser_facture(texte: str) -> dict:
    """Essaie Groq, bascule sur Mistral si confiance faible ou erreur."""

    # ── Tentative Groq ────────────────────────────────
    if groq_client:
        print("🤖 Tentative Groq...")
        resultat = analyser_avec_llm(texte)
        if resultat and resultat.get("confiance") != "faible":
            resultat["_source"] = "groq"
            print(f"✅ Groq réussi — confiance : {resultat['confiance']}")
            return resultat
        print(f"⚠️ Groq insuffisant (confiance={resultat.get('confiance') if resultat else 'erreur'}) → fallback Mistral")

    # ── Fallback Mistral ──────────────────────────────
    resultat_mistral = analyser_avec_mistral(texte)
    if resultat_mistral:
        return resultat_mistral

    # ── Échec total ───────────────────────────────────
    print("❌ Les deux LLM ont échoué")
    return {
        "fournisseur": None, "type_energie": None,
        "quantite": None, "unite": None,
        "date_facture": None, "montant_dh": None,
        "confiance": "faible",
        "note": "Extraction impossible — vérification manuelle requise"
    }


@router.post("/upload-pdf")
async def upload_pdf(fichier: UploadFile = File(...)):
    """Reçoit un PDF, extrait et analyse les données"""

    print(f"\n{'='*50}")
    print(f"📤 Fichier reçu : {fichier.filename}")
    print(f"{'='*50}")

    # Vérifie l'extension
    if not fichier.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Fichier PDF requis")

    # Lit le fichier
    try:
        contenu = await fichier.read()
        print(f"📦 Taille : {len(contenu)} bytes")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture fichier : {str(e)}")

    if len(contenu) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide")

    # Extrait le texte
    texte = extraire_texte_pdf(contenu)
    print(f"📝 Texte total : {len(texte)} caractères")

    if not texte.strip():
        # PDF scanné sans texte — retourne données de base
        print("⚠️ Aucun texte extrait - PDF scanné")
        return JSONResponse({
            "message": "PDF scanné détecté ⚠️",
            "fichier": fichier.filename,
            "donnees_extraites": {
                "fournisseur": "ONEE",
                "type_energie": "electricity",
                "quantite": None,
                "unite": "kWh",
                "date_facture": None,
                "confiance": "faible",
                "note": "PDF scanné - saisie manuelle requise"
            },
            "texte_brut_debut": ""
        })

    # Affiche le texte brut pour déboguer les extractions ratées
    print(f"\n📄 TEXTE EXTRAIT (1500 premiers caractères) :\n{'-'*40}")
    print(texte[:1500])
    print('-'*40)

    # Analyse avec LLM (Groq → Mistral si nécessaire)
    donnees = analyser_facture(texte)

    return {
        "message": "PDF analysé avec succès ✅",
        "fichier": fichier.filename,
        "donnees_extraites": donnees,
        "texte_brut_debut": texte[:300]
    }


@router.post("/valider-extraction")
async def valider_extraction(donnees: dict):
    """Valide et enregistre les données extraites"""
    from database import get_connection

    required = ["type_energie", "quantite", "unite", "date_facture"]
    for champ in required:
        if donnees.get(champ) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Champ manquant : {champ}"
            )

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO activities (source, quantity, unit, date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            donnees["type_energie"],
            float(donnees["quantite"]),
            donnees["unite"],
            donnees["date_facture"]
        ))

        activity_id = cursor.fetchone()["id"]

        cursor.execute("""
            SELECT factor, scope FROM emission_factors
            WHERE energy_type = %s
        """, (donnees["type_energie"],))

        factor_row = cursor.fetchone()
        co2_kg = 0

        if factor_row:
            co2_kg = float(donnees["quantite"]) * factor_row["factor"]
            cursor.execute("""
                INSERT INTO emissions (activity_id, co2_kg, scope)
                VALUES (%s, %s, %s)
            """, (activity_id, co2_kg, factor_row["scope"]))

        conn.commit()

        return {
            "message": "✅ Données enregistrées !",
            "activity_id": activity_id,
            "co2_kg": round(co2_kg, 2),
            "co2_tonnes": round(co2_kg / 1000, 4)
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()