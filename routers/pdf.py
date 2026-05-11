# routers/pdf.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pdfplumber
import json
import os
import re
import io
import base64
import tempfile
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

GROQ_MODEL        = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

print(f"[LLM]    Groq texte  — {GROQ_MODEL}")
print(f"[OCR]    Groq vision — {GROQ_VISION_MODEL}  (PDFs scannés)")


# ── Groq texte ────────────────────────────────────────────────────────────────

def groq_chat(prompt: str, temperature: float = 0.1, max_tokens: int = 500) -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Groq vision (OCR scans) ───────────────────────────────────────────────────

def groq_vision_ocr(img_png_bytes: bytes, page_num: int) -> str:
    """
    Envoie une image PNG à Groq Vision pour transcription.
    Retourne le texte brut de la page (pas d'analyse, juste le texte visible).
    """
    try:
        b64 = base64.b64encode(img_png_bytes).decode("utf-8")
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        resp = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcris TOUT le texte visible sur cette facture. "
                                "Conserve les montants, dates, quantités, unités, nom du fournisseur. "
                                "Texte brut uniquement — pas d'analyse, pas de JSON."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=1500,
            temperature=0.0,
        )
        texte = resp.choices[0].message.content.strip()
        print(f"   Vision page {page_num + 1} : {len(texte)} car.")
        return texte

    except Exception as e:
        print(f"❌ Groq Vision page {page_num + 1} : {e}")
        return ""


# ── Conversion PDF → images PNG ───────────────────────────────────────────────

def _page_vers_png(tmp_path: str, page_idx: int, dpi: int = 300) -> bytes:
    """Convertit une page PDF en PNG (bytes) via PyMuPDF."""
    try:
        import fitz
        doc  = fitz.open(tmp_path)
        page = doc[page_idx]
        mat  = fitz.Matrix(dpi / 72, dpi / 72)
        pix  = page.get_pixmap(matrix=mat)
        png  = pix.tobytes("png")
        doc.close()
        return png
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PyMuPDF absent — pip install pymupdf",
        )


# ── Pré-extraction regex ──────────────────────────────────────────────────────

def _normaliser_date(valeur: str) -> str:
    """
    Convertit une date brute en YYYY-MM-DD.
    Accepte : DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD.
    Retourne None si invalide ou hors plage (> 5 ans passés ou > 60 j futurs).
    """
    from datetime import date, timedelta
    if not valeur:
        return None
    valeur = valeur.strip()
    formats = [
        ("%d/%m/%Y", None), ("%d-%m-%Y", None), ("%d.%m.%Y", None),
        ("%Y-%m-%d", None), ("%d/%m/%y", None), ("%d-%m-%y", None),
    ]
    parsed = None
    for fmt, _ in formats:
        try:
            from datetime import datetime
            parsed = datetime.strptime(valeur, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    today    = date.today()
    min_date = today.replace(year=today.year - 5)
    max_date = today + timedelta(days=60)
    if parsed < min_date or parsed > max_date:
        return None
    return parsed.strftime("%Y-%m-%d")


def _preextrait_regex(texte: str) -> dict:
    h = {}

    kwh = re.findall(r"([\d\s.,]+)\s*kWh", texte, re.IGNORECASE)
    if kwh:
        h["kwh_trouves"] = [k.strip() for k in kwh[:3]]

    litres = re.findall(r"([\d\s.,]+)\s*(?:litres?|litre\b)", texte, re.IGNORECASE)
    if litres:
        h["litres_trouves"] = [l.strip() for l in litres[:3]]

    m3 = re.findall(r"([\d\s.,]+)\s*m[³3]", texte, re.IGNORECASE)
    if m3:
        h["m3_trouves"] = [m.strip() for m in m3[:3]]

    montants = re.findall(
        r"([\d\s]{1,8}[.,]\d{2})\s*(?:DH|MAD|€|EUR)", texte, re.IGNORECASE
    )
    if montants:
        h["montants_trouves"] = list(dict.fromkeys(m.strip() for m in montants))[:5]

    # Dates d'émission : cherche les labels "Date" proches d'une date
    dates_emission = re.findall(
        r"(?:Date\s*(?:de\s*)?(?:facturation|facture|[eé]mission|[eé]tablissement|[eéè]dition)?)"
        r"\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        texte, re.IGNORECASE,
    )
    # Dates de période (à éviter) : "Du X au Y", "Période : X - Y"
    dates_periode = re.findall(
        r"(?:[Pp][eé]riode|[Dd]u|[Aa]u|[Dd]ate\s+de\s+(?:d[eé]but|fin))"
        r"\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        texte, re.IGNORECASE,
    )
    # Toutes les dates brutes
    toutes = re.findall(r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\b", texte)

    # Priorité : dates_emission → toutes sauf celles de période
    periode_set = set(dates_periode)
    candidates  = dates_emission if dates_emission else [d for d in toutes if d not in periode_set]
    valides     = [_normaliser_date(d) for d in dict.fromkeys(candidates)]
    valides     = [v for v in valides if v]

    if valides:
        h["dates_emission"] = valides[:3]
    if dates_periode:
        h["dates_periode"] = list(dict.fromkeys(dates_periode))[:2]

    nums = re.findall(
        r"(?:N[°o]|Num[eé]ro|FACT?U?R?E?)[:\s]*([A-Z0-9\-/]{4,20})",
        texte, re.IGNORECASE,
    )
    if nums:
        h["numeros_trouves"] = list(dict.fromkeys(nums))[:3]

    return h


# ── Extraction hybride ────────────────────────────────────────────────────────

def extraire_texte_pdf(fichier_bytes: bytes):
    """
    Page par page :
      • pdfplumber  → texte natif + tableaux  (rapide)
      • Groq Vision → pages scannées (image)  (si < 50 chars natifs)
    Retourne (texte_complet: str, hints_regex: dict)
    """
    texte_complet = ""
    tableaux_str  = ""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(fichier_bytes)
        tmp_path = tmp.name

    pages_a_vision = []

    try:
        # ── Pass 1 : pdfplumber ─────────────────────────────────────────────
        with pdfplumber.open(tmp_path) as pdf:
            nb = len(pdf.pages)
            print(f"📄 PDF : {nb} page(s)")

            for i, page in enumerate(pdf.pages):
                texte_page = page.extract_text() or ""

                for table in (page.extract_tables() or []):
                    for row in table:
                        row_str = " | ".join(
                            str(c or "").strip() for c in row if c
                        )
                        if row_str:
                            tableaux_str += row_str + "\n"

                if len(texte_page.strip()) >= 50:
                    texte_complet += texte_page + "\n"
                    print(f"   Page {i+1} : texte natif ({len(texte_page)} car.)")
                else:
                    pages_a_vision.append(i)
                    print(f"   Page {i+1} : image/scan → Groq Vision")

        # ── Pass 2 : Groq Vision sur pages scannées ─────────────────────────
        if pages_a_vision:
            print(f"\n🔍 {len(pages_a_vision)} page(s) scannée(s) → Groq Vision")
            for i in pages_a_vision:
                png_bytes = _page_vers_png(tmp_path, i, dpi=300)
                texte_vision = groq_vision_ocr(png_bytes, i)
                if texte_vision:
                    texte_complet += texte_vision + "\n"

        if tableaux_str:
            texte_complet += "\n[TABLEAUX]\n" + tableaux_str

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur extraction : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture PDF : {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    hints = _preextrait_regex(texte_complet)
    print(f"📊 Regex hints : {hints}")
    return texte_complet, hints


# ── Analyse LLM ───────────────────────────────────────────────────────────────

def calculer_confiance(donnees: dict) -> str:
    champs  = ["fournisseur", "quantite", "date_facture", "montant_dh"]
    remplis = sum(1 for c in champs if donnees.get(c) is not None)
    if remplis == 4: return "haute"
    if remplis >= 2: return "moyenne"
    return "faible"


def normaliser(donnees: dict) -> dict:
    if donnees.get("type_energie"):
        t = donnees["type_energie"].lower().strip()
        if t in ["electricite", "électricité", "electric", "electricity"]:
            t = "electricity"
        elif t in ["diesel", "gasoil", "carburant", "fioul", "fuel"]:
            t = "fuel"
        elif t in ["gaz", "gas naturel", "gaz naturel", "gas"]:
            t = "gas"
        donnees["type_energie"] = t

    unites = {"electricity": "kWh", "fuel": "litres", "gas": "m3"}
    if donnees.get("type_energie") in unites:
        donnees["unite"] = unites[donnees["type_energie"]]

    for champ in ["quantite", "montant_dh"]:
        if donnees.get(champ) is not None:
            try:
                donnees[champ] = float(
                    str(donnees[champ]).replace(",", ".").replace(" ", "")
                )
            except Exception:
                donnees[champ] = None

    # Validation et normalisation de la date de facture
    if donnees.get("date_facture"):
        date_ok = _normaliser_date(str(donnees["date_facture"]))
        if date_ok:
            donnees["date_facture"] = date_ok
        else:
            print(f"⚠️  Date rejetée (hors plage ou format invalide) : {donnees['date_facture']}")
            donnees["date_facture"] = None

    donnees["confiance"] = calculer_confiance(donnees)
    return donnees


def analyser_avec_llm(texte: str, hints: dict = None) -> dict:
    hints_bloc = ""
    if hints:
        lignes = []
        if hints.get("kwh_trouves"):
            lignes.append(f"• kWh détectés         : {hints['kwh_trouves']}")
        if hints.get("litres_trouves"):
            lignes.append(f"• Litres détectés      : {hints['litres_trouves']}")
        if hints.get("m3_trouves"):
            lignes.append(f"• m³ détectés          : {hints['m3_trouves']}")
        if hints.get("montants_trouves"):
            lignes.append(f"• Montants DH/€        : {hints['montants_trouves']}")
        if hints.get("dates_emission"):
            lignes.append(f"• Date(s) émission     : {hints['dates_emission']}  ← UTILISE CES DATES")
        if hints.get("dates_periode"):
            lignes.append(f"• Dates période conso  : {hints['dates_periode']}  ← NE PAS UTILISER comme date_facture")
        if hints.get("numeros_trouves"):
            lignes.append(f"• N° facture           : {hints['numeros_trouves']}")
        if lignes:
            hints_bloc = (
                "\n═══ INDICES PRÉ-EXTRAITS (utilise-les en priorité) ═══\n"
                + "\n".join(lignes) + "\n"
            )

    prompt = f"""Tu es un expert en factures énergétiques marocaines. Extrais les données.
{hints_bloc}
═══ TEXTE DU DOCUMENT ═══
{texte[:6000]}

═══ RÈGLES ═══
TYPE D'ÉNERGIE :
- Électricité : kWh, ONEE, Office National, consommation active
- Fuel/Diesel  : gasoil, diesel, litres, carburant, Afriquia, Total Maroc
- Gaz naturel  : gaz naturel, m3, m³

QUANTITÉ : priorité à la valeur étiquetée kWh/L/m³. Virgule=décimale, point=milliers.
DATE FACTURE :
- Cherche : "Date", "Date de facturation", "Date d'émission", "Émis le", "Établi le"
- C'est la date de GÉNÉRATION de la facture, PAS la période de consommation
- Ignore : "Période du X au Y", "Date de début", "Date de fin", deux dates séparées par "-"
- Format de sortie : YYYY-MM-DD obligatoire
MONTANT  : TTC / Total / Net à payer en DH/MAD
FOURNISSEUR : nom en haut du document

═══ RÉPONSE (JSON uniquement) ═══
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
        texte_reponse = groq_chat(prompt, temperature=0.1, max_tokens=500)
        print(f"🤖 Groq brut : {texte_reponse}")

        debut = texte_reponse.find("{")
        fin   = texte_reponse.rfind("}") + 1
        if debut != -1 and fin > debut:
            texte_reponse = texte_reponse[debut:fin]

        donnees = normaliser(json.loads(texte_reponse))
        donnees["_source"] = "groq"
        print(f"✅ Données : {donnees}")
        return donnees

    except json.JSONDecodeError:
        print("❌ JSON invalide")
        return {
            "fournisseur": None, "type_energie": None,
            "quantite": None, "unite": None,
            "date_facture": None, "montant_dh": None,
            "numero_facture": None, "confiance": "faible",
        }
    except Exception as e:
        print(f"❌ Erreur Groq : {e}")
        return {
            "fournisseur": None, "type_energie": None,
            "quantite": None, "unite": None,
            "date_facture": None, "montant_dh": None,
            "numero_facture": None, "confiance": "faible",
            "note": str(e),
        }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/upload-pdf")
async def upload_pdf(fichier: UploadFile = File(...)):
    print(f"\n{'='*50}")
    print(f"📤 {fichier.filename}")
    print(f"{'='*50}")

    if not fichier.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Fichier PDF requis")

    contenu = await fichier.read()
    if len(contenu) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide")

    print(f"📦 {len(contenu)} bytes")

    texte, hints = extraire_texte_pdf(contenu)
    print(f"📝 Texte total : {len(texte)} car.")

    if not texte.strip():
        return JSONResponse({
            "message": "Aucun texte extrait",
            "fichier": fichier.filename,
            "donnees_extraites": {
                "fournisseur": None, "type_energie": None,
                "quantite": None, "unite": None,
                "date_facture": None, "confiance": "faible",
                "note": "PDF illisible",
            },
            "texte_brut_debut": "",
        })

    donnees = analyser_avec_llm(texte, hints)

    return {
        "message": "PDF analysé ✅",
        "fichier": fichier.filename,
        "donnees_extraites": donnees,
        "texte_brut_debut": texte[:300],
    }


@router.post("/valider-extraction")
async def valider_extraction(donnees: dict):
    from database import get_connection

    required = ["type_energie", "quantite", "unite", "date_facture"]
    for champ in required:
        if donnees.get(champ) is None:
            raise HTTPException(status_code=400, detail=f"Champ manquant : {champ}")

    source_document = donnees.pop("source_document", None)
    methode_saisie  = donnees.pop("methode_saisie",  "pdf_auto")

    conn   = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO activities (source, quantity, unit, date, source_document, methode_saisie)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (donnees["type_energie"], float(donnees["quantite"]),
              donnees["unite"], donnees["date_facture"],
              source_document, methode_saisie))

        activity_id = cursor.fetchone()["id"]

        cursor.execute("""
            SELECT factor, scope FROM emission_factors WHERE energy_type = %s
        """, (donnees["type_energie"],))

        factor_row = cursor.fetchone()
        co2_kg     = 0

        if factor_row:
            co2_kg = float(donnees["quantite"]) * factor_row["factor"]
            cursor.execute("""
                INSERT INTO emissions (activity_id, co2_kg, scope)
                VALUES (%s, %s, %s)
            """, (activity_id, co2_kg, factor_row["scope"]))

        cursor.execute("""
            INSERT INTO audit_log (activity_id, changement, raison)
            VALUES (%s, %s, %s)
        """, (
            activity_id,
            f"Création — {donnees['type_energie']} {donnees['quantite']} {donnees['unite']} le {donnees['date_facture']}",
            f"Source : {source_document or 'non précisé'} | Méthode : {methode_saisie}",
        ))

        conn.commit()
        return {
            "message":         "✅ Données enregistrées !",
            "activity_id":     activity_id,
            "co2_kg":          round(co2_kg, 2),
            "co2_tonnes":      round(co2_kg / 1000, 4),
            "source_document": source_document,
            "methode_saisie":  methode_saisie,
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
