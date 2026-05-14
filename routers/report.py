# routers/report.py
# Rapport PDF CBAM officiel — 8 pages
# Règlement UE 2023/956 + 2025/2620 | GHG Protocol Rev. 2024 | ISO 14064

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from database import get_connection
from cbam_engine import calculer_conformite, PRIX_CARBONE_EU
from cbam_reference_complete import get_colonne_obligatoire, CBAM_REFERENCE
import io, os, re
from datetime import datetime
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from services.report import generate_cbam_declaration_report
load_dotenv()

from pydantic import BaseModel
from typing import Optional

class RapportRequest(BaseModel):
    # Période de déclaration CBAM
    trimestre:             Optional[int]   = None   # 1=Q1 2=Q2 3=Q3 4=Q4 (auto si None)
    annee:                 Optional[int]   = None   # auto = année courante
    # Goods imported (Section 2 CBAM)
    quantite_importee:     float           = 0.0
    procedure_douaniere:   str             = "40"   # 40 = libération en libre circulation
    pays_origine:          str             = "MA"   # MA = Maroc
    # Données installation
    operator_id:           str             = ""
    nom_installation:      str             = ""
    ville_installation:    str             = ""
    contact_operateur:     str             = ""
    # Méthode de détermination
    methode_determination: str             = "actual_data"
    methodologie:          str             = "commission_rules"
    # ── Champs nouveaux pour le builder v2 (services/report) ─────────────
    lang:                  str             = "fr"   # "fr" ou "en"
    eori:                  str             = ""     # N° EORI douanier
    nace:                  str             = ""     # Code NACE (ex: 24.10)
    o3ci_id:               str             = ""     # ID registre O3CI
    capacite_t_an:         float           = 0.0   # Capacité nominale (t/an)
    destinataire:          str             = ""     # Importateur UE (recipient)
    verifier_nom:          str             = ""     # Organisme vérificateur
    verifier_accreditation: str            = ""     # N° accréditation
    verifier_pays:         str             = "EU"   # Pays vérificateur

router = APIRouter()

_SECTEUR_MOT_CLE = {
    "Acier/Fer": "steel",    "Aluminium": "aluminium",
    "Ciment":    "cement",   "Engrais":   "fertiliser",
    "Hydrogène": "hydrogen",
}
_SECTEUR_CBAM_KEY = {
    "Acier/Fer": "Iron & Steel", "Aluminium": "Aluminium",
    "Ciment":    "Cement",       "Engrais":   "Fertilisers",
    "Hydrogène": "Hydrogen",
}

GLOSSAIRE = [
    ("CBAM",            "Carbon Border Adjustment Mechanism — taxe carbone aux frontières de l'UE"),
    ("MRV",             "Monitoring, Reporting, Verification — surveillance, déclaration, vérification"),
    ("Scope 1",         "Émissions directes : fuel, gaz naturel, procédés de combustion"),
    ("Scope 2",         "Émissions indirectes liées à l'électricité achetée au réseau"),
    ("Intensité",       "Émissions CO2 par tonne de produit fabriqué (tCO2e/tonne)"),
    ("Benchmark",       "Seuil officiel UE d'émissions par secteur et route de production"),
    ("Column A",        "Calcul CBAM excluant les émissions Scope 2 (fer/acier, aluminium, H2)"),
    ("Column B",        "Calcul CBAM incluant les émissions Scope 2 (ciment, engrais)"),
    ("EU ETS",          "Système européen d'échange de quotas d'émission"),
    ("GHG Protocol",    "Norme comptable internationale des gaz à effet de serre"),
    ("ISO 14064",       "Norme de quantification et rapport des émissions GES"),
    ("BMG",             "Benchmark de référence officiel (Annex III Règlement UE 2025/2620)"),
]


# ══════════════════════════════════════════════════════════════════════════════
# DONNÉES DEPUIS POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

PRIX_CARBONE_MAROC = 0.0  # Maroc : aucun mecanisme ETS reconnu par la Commission Europeenne (Art. 9 Regl. 2023/956)

_TRIMESTRE_DEBUTS = {1: "01/01", 2: "01/04", 3: "01/07", 4: "01/10"}
_TRIMESTRE_FINS   = {1: "31/03", 2: "30/06", 3: "30/09", 4: "31/12"}

def _periode_label(trimestre: int, annee: int) -> str:
    return f"Q{trimestre} {annee}  ({_TRIMESTRE_DEBUTS[trimestre]}/{annee} - {_TRIMESTRE_FINS[trimestre]}/{annee})"


def _get_donnees():
    conn = get_connection()
    conn.autocommit = True   # chaque requête est indépendante — une erreur n'annule pas les suivantes
    cursor = conn.cursor()

    profil = {}
    try:
        cursor.execute("SELECT * FROM company_profile ORDER BY id LIMIT 1")
        row_p = cursor.fetchone()
        profil = dict(row_p) if row_p else {}
    except Exception:
        pass

    totaux = {"total_co2_kg": 0, "nb_activites": 0}
    try:
        cursor.execute("""
            SELECT SUM(e.co2_kg) as total_co2_kg, COUNT(DISTINCT a.id) as nb_activites
            FROM activities a JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true AND e.actif = true
        """)
        row = cursor.fetchone()
        if row:
            totaux = dict(row)
    except Exception:
        pass

    par_scope = {}
    try:
        cursor.execute("""
            SELECT e.scope, SUM(e.co2_kg) as co2_kg
            FROM emissions e JOIN activities a ON a.id = e.activity_id
            WHERE a.actif = true AND e.actif = true
            GROUP BY e.scope ORDER BY e.scope
        """)
        par_scope = {row["scope"]: float(row["co2_kg"]) for row in cursor.fetchall()}
    except Exception:
        pass

    par_source = []
    try:
        cursor.execute("""
            SELECT a.source, SUM(a.quantity) as total_qty, a.unit, SUM(e.co2_kg) as co2_kg
            FROM activities a JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true AND e.actif = true
            GROUP BY a.source, a.unit ORDER BY co2_kg DESC
        """)
        par_source = [dict(r) for r in cursor.fetchall()]
    except Exception:
        pass

    par_mois = []
    try:
        cursor.execute("""
            SELECT TO_CHAR(a.date, 'YYYY-MM') as mois, SUM(e.co2_kg) as co2_kg
            FROM activities a JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true AND e.actif = true
            GROUP BY mois ORDER BY mois DESC LIMIT 6
        """)
        par_mois = [dict(r) for r in cursor.fetchall()]
    except Exception:
        pass

    activites = []
    try:
        cursor.execute("""
            SELECT a.id, a.source, a.quantity, a.unit,
                   TO_CHAR(a.date, 'DD/MM/YYYY') as date_fmt,
                   e.co2_kg, e.scope
            FROM activities a JOIN emissions e ON e.activity_id = a.id
            WHERE a.actif = true AND e.actif = true
            ORDER BY a.date DESC LIMIT 30
        """)
        activites = [dict(r) for r in cursor.fetchall()]
    except Exception:
        pass

    journal = []
    try:
        cursor.execute("""
            SELECT activity_id, champ_modifie, ancienne_val, nouvelle_val,
                   raison, TO_CHAR(modifie_le, 'DD/MM/YYYY HH24:MI') as date_fmt
            FROM journal_modifications
            ORDER BY modifie_le DESC LIMIT 15
        """)
        journal = [dict(r) for r in cursor.fetchall()]
    except Exception:
        pass

    facteurs = []
    try:
        cursor.execute("SELECT energy_type, factor, unit, scope FROM emission_factors")
        facteurs = [dict(r) for r in cursor.fetchall()]
    except Exception:
        pass

    cursor.close()
    conn.close()
    return profil, totaux, par_scope, par_source, par_mois, activites, journal, facteurs


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMANDATIONS LLM (Groq)
# ══════════════════════════════════════════════════════════════════════════════

def _recs_defaut(conformite=None):
    base = [
        "Audit énergétique complet : identifiez les équipements énergivores et planifiez "
        "leur remplacement par des équipements classe A+ pour réduire le Scope 2 de 15-25%.",
        "Transition vers les énergies renouvelables : contractualisez un PPA (Power Purchase "
        "Agreement) avec un fournisseur d'énergie verte — élimine les émissions Scope 2.",
        "Récupération de chaleur fatale : installez des échangeurs thermiques sur les équipements "
        "à haute température pour réduire la consommation de fuel/gaz de 10-20%.",
        "Monitoring IoT temps réel : déployez des capteurs sur les équipements majeurs pour "
        "détecter les dérives de consommation et agir avant tout dépassement CBAM.",
    ]
    if conformite and not conformite.get("conforme"):
        marge = abs(conformite.get("marge_pct", 0))
        base.insert(0,
            f"Action urgente CBAM : votre intensité dépasse le benchmark de {marge:.1f}%. "
            "Priorisez la réduction du Scope 1 (fuel/gaz) qui impacte directement la Colonne A."
        )
    return base[:4]


def _generer_recommandations(total_co2_t, scope1_t, scope2_t, conformite, profil):
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        conf_txt = ""
        if conformite and conformite.get("valide") and "conforme" in conformite:
            conf_txt = (
                f"Statut CBAM : {'CONFORME' if conformite['conforme'] else 'NON CONFORME'}\n"
                f"Intensité réelle : {conformite.get('intensite_reelle', 0):.4f} tCO2e/t\n"
                f"Benchmark : {conformite.get('benchmark', 0):.4f} tCO2e/t\n"
                f"Marge : {conformite.get('marge_pct', 0):.2f}%\n"
                f"Taxe estimée : {conformite.get('exposition_financiere', {}).get('taxe_estimee_euro', 0):.2f} €\n"
            )

        prompt = (
            "Tu es Dr. CarbonIQ, expert CBAM et réduction carbone industrielle.\n"
            f"Données entreprise :\n"
            f"- Total CO2 : {total_co2_t:.3f} tCO2e\n"
            f"- Scope 1 (direct) : {scope1_t:.3f} tCO2e\n"
            f"- Scope 2 (électricité) : {scope2_t:.3f} tCO2e\n"
            f"- Secteur : {profil.get('secteur', 'Non précisé')}\n"
            f"- Route : {profil.get('route_production', 'Non précisée')}\n"
            f"{conf_txt}\n"
            "Génère EXACTEMENT 4 recommandations concrètes et chiffrées.\n"
            "Format : numérotées 1. 2. 3. 4. — max 2 phrases chacune.\n"
            "Réponds uniquement en français."
        )

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=500
        )
        text = resp.choices[0].message.content.strip()
        recs  = re.findall(r'\d+\.\s+(.+?)(?=\n\d+\.|\Z)', text, re.DOTALL)
        recs  = [r.strip().replace('\n', ' ') for r in recs if r.strip()]
        return recs[:4] if len(recs) >= 2 else _recs_defaut(conformite)
    except Exception:
        return _recs_defaut(conformite)


# ══════════════════════════════════════════════════════════════════════════════
# GRAPHIQUES REPORTLAB
# ══════════════════════════════════════════════════════════════════════════════

def _camembert_scope(scope1, scope2, colors):
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.piecharts import Pie

    d   = Drawing(220, 180)
    pie = Pie()
    pie.x, pie.y      = 40, 20
    pie.width = pie.height = 140

    total = (scope1 or 0.001) + (scope2 or 0.001)
    pie.data   = [scope1 or 0.001, scope2 or 0.001]
    pie.labels = [
        f"Scope 1\n{scope1/1000:.2f}t\n({scope1/total*100:.0f}%)",
        f"Scope 2\n{scope2/1000:.2f}t\n({scope2/total*100:.0f}%)",
    ]
    pie.slices[0].fillColor   = colors.HexColor('#3fb950')
    pie.slices[1].fillColor   = colors.HexColor('#58a6ff')
    pie.slices[0].strokeColor = colors.HexColor('#091413')
    pie.slices[1].strokeColor = colors.HexColor('#091413')
    pie.slices[0].strokeWidth = 1
    pie.slices[1].strokeWidth = 1
    pie.slices.labelRadius    = 1.35
    d.add(pie)
    return d


def _barres_source(par_source, colors, cm):
    from reportlab.graphics.shapes import Drawing, Rect, String, Line

    sources = par_source[:4]
    if not sources:
        return Drawing(300, 10)

    vals      = [float(s['co2_kg']) for s in sources]
    max_val   = max(vals) or 1
    W, H      = 320, 160
    bar_w     = min(50, (W - 60) // len(sources) - 10)
    gap       = (W - 60 - bar_w * len(sources)) // (len(sources) + 1)
    src_colors = ['#3fb950', '#58a6ff', '#e3b341', '#f85149']

    d = Drawing(W, H + 30)

    # Y-axis
    d.add(Line(50, 10, 50, H, strokeColor=colors.HexColor('#1a3828'), strokeWidth=1))
    # X-axis
    d.add(Line(50, 10, W - 10, 10, strokeColor=colors.HexColor('#1a3828'), strokeWidth=1))

    for i, s in enumerate(sources):
        x      = 50 + gap + i * (bar_w + gap)
        h_bar  = int((float(s['co2_kg']) / max_val) * (H - 20))
        d.add(Rect(x, 10, bar_w, h_bar,
                   fillColor=colors.HexColor(src_colors[i % 4]),
                   strokeColor=None))
        label = s['source'][:10]
        d.add(String(x + bar_w // 2, 0, label, fontSize=8,
                     fillColor=colors.HexColor('#7a9e8a'),
                     textAnchor='middle'))
        val_str = f"{float(s['co2_kg'])/1000:.2f}t"
        d.add(String(x + bar_w // 2, 10 + h_bar + 2, val_str, fontSize=7,
                     fillColor=colors.HexColor('#e6edf3'),
                     textAnchor='middle'))

    # Y-axis ticks
    for pct in [25, 50, 75, 100]:
        y = 10 + int((pct / 100) * (H - 20))
        d.add(Line(45, y, 50, y, strokeColor=colors.HexColor('#1a3828'), strokeWidth=1))
        val_tick = max_val * pct / 100 / 1000
        d.add(String(44, y - 4, f"{val_tick:.1f}t", fontSize=7,
                     fillColor=colors.HexColor('#7a9e8a'), textAnchor='end'))

    return d


def _jauge_conformite(intensite, benchmark, conforme, colors, cm):
    from reportlab.graphics.shapes import Drawing, Rect, Line, String

    W, H      = 420, 50
    max_val   = max(intensite, benchmark) * 1.25 or 1

    d = Drawing(W, H + 40)

    # Fond gris
    d.add(Rect(0, 30, W, H, fillColor=colors.HexColor('#1a3828'), strokeColor=None))

    # Zone verte (0 → benchmark)
    safe_w = min(int((benchmark / max_val) * W), W)
    d.add(Rect(0, 30, safe_w, H, fillColor=colors.HexColor('#2ea043'), strokeColor=None))

    # Zone rouge (benchmark → intensite si dépassement)
    if intensite > benchmark:
        danger_w = min(int((intensite / max_val) * W), W)
        d.add(Rect(safe_w, 30, danger_w - safe_w, H,
                   fillColor=colors.HexColor('#f85149'), strokeColor=None))

    # Ligne benchmark (jaune)
    d.add(Line(safe_w, 20, safe_w, 30 + H + 10,
               strokeColor=colors.HexColor('#e3b341'), strokeWidth=2))
    d.add(String(safe_w - 2, 16, f"Bmg {benchmark:.4f}", fontSize=8,
                 fillColor=colors.HexColor('#e3b341'), textAnchor='end'))

    # Marqueur intensité réelle (blanc)
    int_x = min(int((intensite / max_val) * W), W - 2)
    d.add(Line(int_x, 22, int_x, 30 + H + 8,
               strokeColor=colors.white, strokeWidth=3))
    d.add(String(int_x + 3, 22, f"Réel {intensite:.4f}", fontSize=8,
                 fillColor=colors.white))

    # Labels axes
    d.add(String(0, 16, "0", fontSize=8, fillColor=colors.HexColor('#7a9e8a')))
    d.add(String(W - 2, 16, f"{max_val:.3f}", fontSize=8,
                 fillColor=colors.HexColor('#7a9e8a'), textAnchor='end'))

    # Légende
    d.add(Rect(0, 0, 12, 10, fillColor=colors.HexColor('#2ea043'), strokeColor=None))
    d.add(String(15, 1, "Zone conforme", fontSize=8, fillColor=colors.HexColor('#7a9e8a')))
    d.add(Rect(110, 0, 12, 10, fillColor=colors.HexColor('#f85149'), strokeColor=None))
    d.add(String(125, 1, "Zone de dépassement", fontSize=8, fillColor=colors.HexColor('#7a9e8a')))

    return d


# ══════════════════════════════════════════════════════════════════════════════
# STYLES COMMUNS
# ══════════════════════════════════════════════════════════════════════════════

def _styles(colors, cm):
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    base = getSampleStyleSheet()

    def s(name, **kw):
        parent = kw.pop('parent', base['Normal'])
        return ParagraphStyle(name, parent=parent, **kw)

    C_BG   = colors.HexColor('#091413')
    C_VERT = colors.HexColor('#3fb950')
    C_BLEU = colors.HexColor('#58a6ff')
    C_TXT  = colors.HexColor('#e6edf3')
    C_MUT  = colors.HexColor('#7a9e8a')
    C_ORNG = colors.HexColor('#e3b341')

    return {
        'cover_h1':  s('cov1',  fontSize=28, textColor=C_VERT,  spaceAfter=8,  leading=32, alignment=1),
        'cover_h2':  s('cov2',  fontSize=20, textColor=C_TXT,   spaceAfter=6,  leading=24, alignment=1),
        'cover_sub': s('covs',  fontSize=11, textColor=C_MUT,   spaceAfter=4,  leading=16, alignment=1),
        'cover_ent': s('cove',  fontSize=16, textColor=C_BLEU,  spaceAfter=4,  leading=20, alignment=1),
        'section':   s('sec',   fontSize=12, textColor=C_BLEU,  spaceBefore=12, spaceAfter=8,
                        parent=base['Heading2']),
        'subsec':    s('sub',   fontSize=10, textColor=C_ORNG,  spaceBefore=6,  spaceAfter=4),
        'body':      s('bod',   fontSize=10, textColor=C_TXT,   spaceAfter=5,   leading=15),
        'small':     s('sml',   fontSize=8,  textColor=C_MUT,   spaceAfter=3,   leading=12),
        'footer':    s('ftr',   fontSize=8,  textColor=C_MUT,   alignment=1),
        'legal':     s('leg',   fontSize=9,  textColor=C_TXT,   spaceAfter=5,   leading=14),
        'rec_num':   s('rnm',   fontSize=11, textColor=C_VERT,  spaceAfter=2,   leading=14),
        'rec_txt':   s('rtx',   fontSize=10, textColor=C_TXT,   spaceAfter=10,  leading=15,
                        leftIndent=16),
    }


def _ts_kv(colors):
    from reportlab.platypus import TableStyle
    C_CARTE = colors.HexColor('#0f2018')
    C_BG    = colors.HexColor('#091413')
    C_BORD  = colors.HexColor('#1a3828')
    C_MUT   = colors.HexColor('#7a9e8a')
    C_TXT   = colors.HexColor('#e6edf3')
    return TableStyle([
        ('FONTSIZE',       (0, 0), (-1, -1), 9),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORD),
        ('PADDING',        (0, 0), (-1, -1), 6),
        ('BACKGROUND',     (0, 0), (0, -1),  C_CARTE),
        ('TEXTCOLOR',      (0, 0), (0, -1),  C_MUT),
        ('ROWBACKGROUNDS', (1, 0), (1, -1),  [C_CARTE, C_BG]),
        ('TEXTCOLOR',      (1, 0), (1, -1),  C_TXT),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
    ])


def _ts_hdr(colors, right_cols=None):
    from reportlab.platypus import TableStyle
    C_CARTE = colors.HexColor('#0f2018')
    C_BG    = colors.HexColor('#091413')
    C_BORD  = colors.HexColor('#1a3828')
    C_VERT  = colors.HexColor('#3fb950')
    C_TXT   = colors.HexColor('#e6edf3')
    cmds = [
        ('FONTSIZE',       (0, 0), (-1, -1), 9),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORD),
        ('PADDING',        (0, 0), (-1, -1), 5),
        ('BACKGROUND',     (0, 0), (-1, 0),  C_BORD),
        ('TEXTCOLOR',      (0, 0), (-1, 0),  C_VERT),
        ('FONTNAME',       (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_CARTE, C_BG]),
        ('TEXTCOLOR',      (0, 1), (-1, -1), C_TXT),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
    ]
    if right_cols:
        for col in right_cols:
            cmds.append(('ALIGN', (col, 0), (col, -1), 'RIGHT'))
    return TableStyle(cmds)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — COUVERTURE
# ══════════════════════════════════════════════════════════════════════════════

def _page_couverture(elems, profil, now, reference, S, colors, cm, Paragraph, Table, TableStyle, Spacer, HRFlowable, req=None, **_):
    nom       = profil.get("nom_entreprise") or "Entreprise"
    secteur   = profil.get("secteur") or "—"
    route     = profil.get("route_production") or "—"
    prod      = profil.get("production_annuelle_tonnes", 0)
    annee     = (req.annee if req and req.annee else None) or datetime.now().year
    trimestre = (req.trimestre if req and req.trimestre else None) or ((datetime.now().month - 1) // 3 + 1)
    periode   = _periode_label(trimestre, annee)

    # Bloc vert en-tête
    cover_top = Table([[Paragraph("🌿 CarbonIQ", S['cover_h1'])]],
                      colWidths=[16*cm])
    cover_top.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f2018')),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('PADDING',    (0, 0), (-1, -1), 20),
        ('BOX',        (0, 0), (-1, -1), 2, colors.HexColor('#3fb950')),
    ]))
    elems.append(Spacer(1, 1.5*cm))
    elems.append(cover_top)
    elems.append(Spacer(1, 1*cm))

    elems.append(Paragraph("RAPPORT DE CONFORMITÉ CBAM", S['cover_h2']))
    elems.append(Paragraph("Mécanisme d'Ajustement Carbone aux Frontières", S['cover_sub']))
    elems.append(Spacer(1, 0.8*cm))
    elems.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#3fb950')))
    elems.append(Spacer(1, 0.8*cm))

    elems.append(Paragraph(nom, S['cover_ent']))
    elems.append(Paragraph(f"Secteur CBAM : {secteur}  ·  Route : {route}", S['cover_sub']))
    elems.append(Paragraph(f"Production annuelle : {prod:,.0f} tonnes", S['cover_sub']))
    elems.append(Spacer(1, 0.8*cm))
    elems.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1a3828')))
    elems.append(Spacer(1, 0.6*cm))

    elems.append(Paragraph(f"Période de référence : {periode}", S['cover_sub']))
    elems.append(Paragraph(f"Référence rapport : {reference}", S['cover_sub']))
    elems.append(Paragraph(f"Généré le : {now}", S['cover_sub']))
    elems.append(Spacer(1, 1.5*cm))

    legal = Table([[
        Paragraph("Règlement UE 2023/956", S['small']),
        Paragraph("Règlement UE 2025/2620", S['small']),
        Paragraph("GHG Protocol Rev. 2024", S['small']),
        Paragraph("ISO 14064", S['small']),
    ]], colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    legal.setStyle(TableStyle([
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f2018')),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#1a3828')),
        ('PADDING',    (0, 0), (-1, -1), 8),
    ]))
    elems.append(legal)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — IDENTIFICATION DE L'INSTALLATION
# ══════════════════════════════════════════════════════════════════════════════

def _page_identification(elems, profil, nb_activites, S, colors, cm, Paragraph, Table, Spacer, HRFlowable, req=None, **_):
    elems.append(Paragraph("1. Identification de l'Installation", S['section']))

    nom     = profil.get("nom_entreprise") or "—"
    secteur = profil.get("secteur") or "—"
    cn      = profil.get("cn_code") or "—"
    route   = profil.get("route_production") or "—"
    prod    = profil.get("production_annuelle_tonnes", 0)
    cbam_k  = _SECTEUR_CBAM_KEY.get(secteur, "—")

    from cbam_reference_complete import CBAM_REFERENCE
    colonne = "—"
    em_ind  = "—"
    if cbam_k and cbam_k in CBAM_REFERENCE:
        colonne = CBAM_REFERENCE[cbam_k]["colonne_obligatoire"]
        em_ind  = CBAM_REFERENCE[cbam_k]["emissions_indirectes"]

    t = Table([
        ["Nom de l'entreprise",     nom],
        ["Pays",                    "Maroc"],
        ["Secteur CBAM officiel",   f"{secteur} ({cbam_k})"],
        ["Code NC produit",         cn],
        ["N° Compte CBAM",          profil.get("numero_compte_cbam") or "— Non renseigné (obligatoire Art. 14 Règl. 2023/956)"],
        ["Route de production",     route],
        ["Production annuelle",     f"{prod:,.0f} tonnes"],
        ["Activités enregistrées",  f"{nb_activites}"],
        ["Colonne CBAM",            f"Colonne {colonne} — obligatoire pour ce secteur"],
        ["Émissions indirectes",    em_ind],
        ["Méthode de calcul",       "EU Calculation Method (Règlement UE 2025/2620, Annexe III)"],
        ["Période de rapport",      _periode_label(
                                        (req.trimestre if req and req.trimestre else None) or ((datetime.now().month-1)//3+1),
                                        (req.annee if req and req.annee else None) or datetime.now().year
                                    )],
        ["Standard MRV",            "GHG Protocol Corporate Standard (Rev. 2024)"],
        ["ID Opérateur",            (req.operator_id if req and req.operator_id else "—")],
        ["Nom installation",        (req.nom_installation if req and req.nom_installation else profil.get("nom_entreprise") or "—")],
        ["Ville installation",      (req.ville_installation if req and req.ville_installation else "—")],
        ["Contact opérateur",       (req.contact_operateur if req and req.contact_operateur else "—")],
    ], colWidths=[6*cm, 10*cm])
    t.setStyle(_ts_kv(colors))
    elems.append(t)
    elems.append(Spacer(1, 0.4*cm))

    # Note réglementaire
    elems.append(Paragraph("Base réglementaire", S['subsec']))
    elems.append(Paragraph(
        "Ce rapport est établi conformément au Règlement (UE) 2023/956 du Parlement Européen "
        "instituant le mécanisme d'ajustement carbone aux frontières, à son règlement d'exécution "
        "(UE) 2025/2620 définissant les benchmarks officiels par secteur et route de production, "
        "et aux exigences de vérification ISO 14064-1 pour la quantification des émissions GES.",
        S['legal']
    ))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2bis — GOODS IMPORTED (Section 2 CBAM — Art. 35 Règl. 2023/956)
# ══════════════════════════════════════════════════════════════════════════════

def _page_marchandises(elems, profil, S, colors, cm, Paragraph, Table, Spacer, HRFlowable, req=None, **_):
    elems.append(Paragraph("2. Marchandises Importées (Goods Imported)", S['section']))

    cn      = profil.get("cn_code") or "—"
    secteur = profil.get("secteur") or "—"
    prod    = profil.get("production_annuelle_tonnes") or 0

    qt_imp   = req.quantite_importee   if req else 0.0
    proc_dou = req.procedure_douaniere if req else "40"
    pays_or  = req.pays_origine        if req else "MA"

    elems.append(Paragraph(
        "Section 2 du formulaire CBAM — Art. 35 Règlement (UE) 2023/956 : "
        "déclaration des marchandises importées soumises au mécanisme CBAM.",
        S['small']
    ))
    elems.append(Spacer(1, 0.3*cm))

    t = Table([
        ["Paramètre",               "Valeur"],
        ["Code NC (CN code)",       cn],
        ["Secteur CBAM",            secteur],
        ["Quantité produite",       f"{prod:,.2f} tonnes"],
        ["Quantité importée",       f"{qt_imp:,.2f} tonnes"],
        ["Procédure douanière",     f"{proc_dou} — libération en libre circulation"],
        ["Pays d'origine",          f"{pays_or} — Maroc"],
        ["Base réglementaire",      "Art. 35 Règl. (UE) 2023/956 — CBAM"],
    ], colWidths=[6*cm, 10*cm])
    t.setStyle(_ts_kv(colors))
    elems.append(t)
    elems.append(Spacer(1, 0.4*cm))

    elems.append(Paragraph(
        "La procédure douanière 40 correspond à la mise en libre circulation "
        "avec imposition simultanée des droits de douane. "
        "Conformément à l'Art. 6 du Règlement (UE) 2023/956, le déclarant CBAM doit "
        "déclarer chaque trimestre la quantité de marchandises importées et leur contenu "
        "carbone incorporé.",
        S['legal']
    ))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — BILAN DES ÉMISSIONS (MRV)
# ══════════════════════════════════════════════════════════════════════════════

def _page_bilan(elems, totaux, par_scope, par_source, par_mois, facteurs,
                S, colors, cm, Paragraph, Table, Spacer, HRFlowable, **_):
    elems.append(Paragraph("3. Bilan des Émissions (MRV)", S['section']))

    total_kg = float(totaux.get("total_co2_kg") or 0)
    s1_kg    = par_scope.get(1, 0)
    s2_kg    = par_scope.get(2, 0)

    # Tableau Scope 1 & 2
    t = Table([
        ["Scope",       "Description",                "kg CO2e",            "tCO2e"],
        ["Scope 1",     "Émissions directes (fuel, gaz)", f"{s1_kg:,.1f}",  f"{s1_kg/1000:.3f}"],
        ["Scope 2",     "Électricité achetée",         f"{s2_kg:,.1f}",     f"{s2_kg/1000:.3f}"],
        ["TOTAL",       "Scope 1 + Scope 2",           f"{total_kg:,.1f}",  f"{total_kg/1000:.3f}"],
    ], colWidths=[2.5*cm, 7*cm, 3.5*cm, 3*cm])
    t.setStyle(_ts_hdr(colors, right_cols=[2, 3]))
    t.setStyle(TableStyle(
        _ts_hdr(colors, right_cols=[2, 3])._cmds + [
            ('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1a3828')),
            ('TEXTCOLOR',  (0, -1), (-1, -1), colors.HexColor('#3fb950')),
        ]
    ))
    elems.append(t)
    elems.append(Spacer(1, 0.5*cm))

    # Graphiques côte à côte
    elems.append(Paragraph("Répartition des émissions", S['subsec']))
    if s1_kg > 0 or s2_kg > 0:
        pie   = _camembert_scope(s1_kg, s2_kg, colors)
        barres = _barres_source(par_source, colors, cm)
        t_graphs = Table([[pie, barres]], colWidths=[8*cm, 9*cm])
        t_graphs.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elems.append(t_graphs)
    elems.append(Spacer(1, 0.4*cm))

    # Tableau par source
    if par_source:
        elems.append(Paragraph("Détail par source d'énergie", S['subsec']))
        rows = [["Source", "Quantité consommée", "Facteur GHG", "kg CO2e", "tCO2e", "Scope"]]
        fmap = {f["energy_type"]: f for f in facteurs}
        for s in par_source:
            src = s["source"]
            f   = fmap.get(src, {})
            rows.append([
                src,
                f"{float(s['total_qty']):.1f} {s['unit']}",
                f"{f.get('factor', '—')} {f.get('unit', '')}",
                f"{float(s['co2_kg']):,.1f}",
                f"{float(s['co2_kg'])/1000:.3f}",
                f"Scope {f.get('scope', '?')}",
            ])
        t2 = Table(rows, colWidths=[2.5*cm, 3.5*cm, 3.5*cm, 2.8*cm, 2*cm, 1.7*cm])
        t2.setStyle(_ts_hdr(colors, right_cols=[3, 4]))
        elems.append(t2)
    elems.append(Spacer(1, 0.4*cm))

    # Évolution mensuelle
    if par_mois:
        elems.append(Paragraph("Évolution mensuelle (6 derniers mois)", S['subsec']))
        mois_rows = [["Mois", "kg CO2e", "tCO2e"]]
        for m in par_mois:
            mois_rows.append([
                m["mois"],
                f"{float(m['co2_kg']):,.1f}",
                f"{float(m['co2_kg'])/1000:.3f}",
            ])
        t3 = Table(mois_rows, colWidths=[4*cm, 6*cm, 6*cm])
        t3.setStyle(_ts_hdr(colors, right_cols=[1, 2]))
        elems.append(t3)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — CONFORMITÉ CBAM
# ══════════════════════════════════════════════════════════════════════════════

def _page_conformite(elems, conformite, profil, par_scope,
                     S, colors, cm, Paragraph, Table, TableStyle, Spacer, HRFlowable, req=None, **_):
    elems.append(Paragraph("3. Analyse de Conformité CBAM", S['section']))

    if not conformite or not conformite.get("valide") or "conforme" not in conformite:
        elems.append(Paragraph(
            "Profil entreprise non configuré. Accédez aux Paramètres pour activer l'analyse CBAM.",
            S['body']
        ))
        return

    conforme  = conformite["conforme"]
    intensite = conformite.get("intensite_reelle", 0)
    benchmark = conformite.get("benchmark", 0)
    marge     = conformite.get("marge_pct", 0)
    excedent  = conformite.get("excedent_tco2", 0)
    risque    = conformite.get("risque", "—")
    fin       = conformite.get("exposition_financiere", {})
    taxe      = fin.get("taxe_estimee_euro", 0)
    prod      = conformite.get("donnees", {}).get("production_tonnes", 0)
    colonne   = conformite.get("produit", {}).get("colonne", "?")

    # Statut principal
    statut_color = colors.HexColor('#2ea043') if conforme else colors.HexColor('#f85149')
    statut_text  = "✅  CONFORME" if conforme else "❌  NON CONFORME"
    t_statut = Table([[Paragraph(statut_text, S['cover_h2'])]],
                     colWidths=[16*cm])
    t_statut.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), statut_color),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('PADDING',    (0, 0), (-1, -1), 14),
    ]))
    elems.append(t_statut)
    elems.append(Spacer(1, 0.4*cm))

    # KPIs principaux
    s1_kg = par_scope.get(1, 0)
    s_total = par_scope.get(1, 0) + par_scope.get(2, 0)
    co2_used = s1_kg if colonne == "A" else s_total

    t_kpi = Table([
        ["Intensité réelle", "Benchmark officiel", "Marge", "Taxe CBAM"],
        [
            f"{intensite:.4f}",
            f"{benchmark:.4f}",
            f"{marge:+.2f}%",
            f"{taxe:,.0f} €",
        ],
        ["tCO2e/tonne", "tCO2e/tonne",
         "Conforme" if conforme else "DÉPASSEMENT",
         "Exposition EU ETS"],
    ], colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    t_kpi.setStyle(TableStyle([
        ('FONTSIZE',   (0, 0), (-1, -1), 9),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 0), (-1, 0),  colors.HexColor('#1a3828')),
        ('TEXTCOLOR',  (0, 0), (-1, 0),  colors.HexColor('#7a9e8a')),
        ('FONTNAME',   (0, 1), (-1, 1),  'Helvetica-Bold'),
        ('FONTSIZE',   (0, 1), (-1, 1),  13),
        ('TEXTCOLOR',  (0, 1), (0, 1),   colors.HexColor('#58a6ff')),
        ('TEXTCOLOR',  (1, 1), (1, 1),   colors.HexColor('#e3b341')),
        ('TEXTCOLOR',  (2, 1), (2, 1),   colors.HexColor('#3fb950') if conforme else colors.HexColor('#f85149')),
        ('TEXTCOLOR',  (3, 1), (3, 1),   colors.HexColor('#3fb950') if taxe == 0 else colors.HexColor('#f85149')),
        ('TEXTCOLOR',  (0, 2), (-1, 2),  colors.HexColor('#7a9e8a')),
        ('FONTSIZE',   (0, 2), (-1, 2),  8),
        ('BACKGROUND', (0, 1), (-1, 2),  colors.HexColor('#0f2018')),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#1a3828')),
        ('PADDING',    (0, 0), (-1, -1), 8),
    ]))
    elems.append(t_kpi)
    elems.append(Spacer(1, 0.5*cm))

    # Alerte seuil 50 tonnes — Règlement UE 2025/2083, Art. 4
    if prod >= 50:
        t_alerte50 = Table([[Paragraph(
            f"ALERTE SEUIL DECLARATIF (Regl. UE 2025/2083, Art. 4) — "
            f"Production {prod:,.0f} t depasse le seuil de 50 t : "
            "declaration CBAM trimestrielle obligatoire aupres des autorites douanieres.",
            S['body']
        )]], colWidths=[16*cm])
        t_alerte50.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#3d2000')),
            ('BOX',        (0, 0), (-1, -1), 2,   colors.HexColor('#e3b341')),
            ('PADDING',    (0, 0), (-1, -1), 10),
        ]))
        elems.append(t_alerte50)
        elems.append(Spacer(1, 0.3*cm))

    # Jauge visuelle
    elems.append(Paragraph("Score de conformité — Intensité vs Benchmark", S['subsec']))
    elems.append(_jauge_conformite(intensite, benchmark, conforme, colors, cm))
    elems.append(Spacer(1, 0.5*cm))

    # Tableau détaillé
    t_det = Table([
        ["Paramètre",              "Valeur"],
        ["Colonne CBAM appliquée", f"Colonne {colonne}"],
        ["CO2 utilisé pour le calcul",
         f"{co2_used/1000:.4f} t ({'Scope 1 uniquement' if colonne=='A' else 'Scope 1+2'})"],
        ["Production",             f"{prod:,.0f} tonnes"],
        ["Intensité réelle",       f"{intensite:.4f} tCO2e/tonne"],
        ["Benchmark officiel",     f"{benchmark:.4f} tCO2e/tonne"],
        ["Marge de conformité",    f"{marge:.2f}%"],
        ["Excédent CO2",           f"{excedent:.4f} tCO2e"],
        ["Niveau de risque",       risque],
        ["Taxe CBAM estimée",      f"{taxe:,.2f} €"],
        ["Prix carbone EU ETS",    f"{fin.get('prix_carbone_euro', PRIX_CARBONE_EU)} €/tonne"],
    ], colWidths=[7*cm, 9*cm])
    t_det.setStyle(_ts_kv(colors))
    elems.append(t_det)
    elems.append(Spacer(1, 0.4*cm))

    # Déduction Article 9 — Prix carbone pays exportateur (Règlement UE 2023/956)
    elems.append(Paragraph("Déduction Article 9 — Prix carbone pays exportateur", S['subsec']))
    deduction_euro = PRIX_CARBONE_MAROC * max(excedent, 0)
    taxe_nette     = max(taxe - deduction_euro, 0)
    t_ded = Table([
        ["Paramètre",                          "Valeur"],
        ["Prix carbone Maroc (ETS éq.)",       f"{PRIX_CARBONE_MAROC:.2f} EUR/tonne"],
        ["Mécanisme de tarification",           "Aucun mécanisme ETS reconnu — déduction = 0 EUR"],
        ["Déduction applicable (Art. 9)",      f"{deduction_euro:,.2f} EUR"],
        ["Taxe CBAM brute estimée",            f"{taxe:,.2f} EUR"],
        ["Taxe CBAM nette après déduction",    f"{taxe_nette:,.2f} EUR"],
    ], colWidths=[7*cm, 9*cm])
    t_ded.setStyle(_ts_kv(colors))
    elems.append(t_ded)
    elems.append(Paragraph(
        "Art. 9 Règl. (UE) 2023/956 : le déclarant peut déduire le prix carbone effectivement "
        "payé dans le pays d'origine. Le Maroc ne dispose pas actuellement d'un mécanisme de "
        "tarification carbone reconnu par la Commission Européenne — déduction applicable : 0 EUR.",
        S['small']
    ))
    elems.append(Spacer(1, 0.3*cm))

    # Changement 4 — Méthode de détermination (Art. 4 Règl. 2025/2620)
    elems.append(Paragraph("Méthode de détermination des émissions", S['subsec']))
    meth_det  = (req.methode_determination if req else None) or "actual_data"
    meth_logi = (req.methodologie          if req else None) or "commission_rules"
    meth_det_label  = "Données réelles mesurées" if meth_det  == "actual_data"      else "Valeurs par défaut (default values)"
    meth_logi_label = "Règles Commission UE (Annexe III Règl. 2025/2620)"            if meth_logi == "commission_rules"   else "Données AIE (IEA data)"
    t_meth = Table([
        ["Paramètre",                   "Valeur"],
        ["Méthode de détermination",    meth_det_label],
        ["Méthodologie appliquée",      meth_logi_label],
        ["Base réglementaire",          "Art. 4 & Annexe III Règl. (UE) 2025/2620"],
        ["Facteur d'activité",          "Mesuré sur site (monitoring continu)"],
    ], colWidths=[7*cm, 9*cm])
    t_meth.setStyle(_ts_kv(colors))
    elems.append(t_meth)
    elems.append(Spacer(1, 0.3*cm))

    # Recommandation moteur
    if conformite.get("recommandation"):
        elems.append(Paragraph("Diagnostic automatique", S['subsec']))
        elems.append(Paragraph(conformite["recommandation"], S['body']))

    # ── DVs Officiels (Règlement UE 2025/2621) ──────────────────────────────
    cn_code_profil = profil.get("cn_code") or ""
    annee_rapport  = (req.annee if req and req.annee else None) or datetime.now().year
    if cn_code_profil and intensite > 0 and prod > 0:
        try:
            from routers.cbam_conformite import calculer_conformite_cbam
            dv_calc = calculer_conformite_cbam(
                country="Morocco",
                cn_code=profil.cn_code,
                co2_scope1_tonnes=scope1_total,
                co2_scope2_tonnes=scope2_total,
                production_tonnes=profil.production_annuelle_tonnes,
                annee=annee_rapport,
                benchmark_tco2_t=benchmark_valeur  # optionnel
            )
            if dv_calc.get("status") == "success":
                elems.append(Spacer(1, 0.4*cm))
                elems.append(Paragraph(
                    "Valeurs Par Défaut officielles — Règlement UE 2025/2621",
                    S['subsec']
                ))
                elems.append(Paragraph(
                    f"Source : {dv_calc['source_fichier']} — Onglet '{dv_calc['source_onglet']}'",
                    S['small']
                ))
                elems.append(Spacer(1, 0.2*cm))

                statut_dv = dv_calc["statut"]
                dv_color  = colors.HexColor('#2ea043') if statut_dv == "CONFORME" else colors.HexColor('#f85149')
                t_dv_stat = Table([[Paragraph(
                    f"{'✅' if statut_dv == 'CONFORME' else '❌'}  DVs : {statut_dv}  —  "
                    f"Économie : {dv_calc['economie_pourcentage']}% sous le mark-up",
                    S['body']
                )]], colWidths=[16*cm])
                t_dv_stat.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), dv_color),
                    ('PADDING',    (0, 0), (-1, -1), 8),
                ]))
                elems.append(t_dv_stat)
                elems.append(Spacer(1, 0.2*cm))

                t_dv = Table([
                    ["Paramètre",                  "Valeur"],
                    ["Produit (Excel)",             dv_calc["description"]],
                    ["Route de production",         dv_calc["route"]],
                    ["DV Scope 1 (direct)",         f"{dv_calc['dv_direct_scope1']:.4f} tCO₂/t"],
                    ["DV Scope 2 (indirect)",       f"{dv_calc['dv_indirect_scope2']:.4f} tCO₂/t"],
                    ["DV Total (seuil CBAM)",       f"{dv_calc['dv_total']:.4f} tCO₂/t"],
                    [f"Mark-up {annee_rapport}",    f"{dv_calc['dv_markup']:.4f} tCO₂/t"],
                    ["Intensité réelle",            f"{dv_calc['intensite_reelle']:.4f} tCO₂/t"],
                    ["Excédent CO₂",                f"{dv_calc['excedent_tco2']:.2f} tCO₂e"],
                    ["Taxe brute (EU ETS)",         f"{dv_calc['taxe_brute']:.2f} €"],
                    [f"Free Allocation {annee_rapport} (×{dv_calc['facteur_free_allocation']:.3f})",
                                                    f"−{dv_calc['reduction_percentage']:.1f}%  →  {dv_calc['taxe_ajustee']:.2f} €"],
                    ["Déduction Article 9 (Maroc)", f"{dv_calc['deduction_article9']:.2f} €"],
                    ["TAXE NETTE DUE",              f"{dv_calc['taxe_nette_due']:.2f} €"],
                ], colWidths=[7*cm, 9*cm])
                t_dv.setStyle(_ts_kv(colors))
                elems.append(t_dv)
                elems.append(Paragraph(
                    "DVs = Valeurs Par Défaut officielles (Annexe I Règlement UE 2025/2621). "
                    "Le mark-up intègre la marge réglementaire appliquée au-dessus du DV total. "
                    "La Free Allocation réduit la taxe brute selon le calendrier de montée en charge CBAM.",
                    S['small']
                ))
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — DONNÉES DE MONITORING DÉTAILLÉES
# ══════════════════════════════════════════════════════════════════════════════

def _page_monitoring(elems, activites, journal, S, colors, cm,
                     Paragraph, Table, Spacer, HRFlowable, **_):
    elems.append(Paragraph("4. Données de Monitoring Détaillées", S['section']))

    if activites:
        elems.append(Paragraph(f"Activités enregistrées (30 dernières — actif=true)", S['subsec']))
        rows = [["#ID", "Source", "Quantité", "Date", "CO2 (kg)", "Scope"]]
        for a in activites:
            rows.append([
                str(a.get("id", "—")),
                a.get("source", "—"),
                f"{float(a.get('quantity', 0)):.1f} {a.get('unit', '')}",
                a.get("date_fmt", "—"),
                f"{float(a.get('co2_kg', 0)):,.1f}",
                f"Scope {a.get('scope', '?')}",
            ])
        t = Table(rows, colWidths=[1.5*cm, 2.5*cm, 3.5*cm, 3*cm, 3.5*cm, 2*cm])
        t.setStyle(_ts_hdr(colors, right_cols=[4]))
        elems.append(t)
    else:
        elems.append(Paragraph("Aucune activité enregistrée.", S['body']))

    elems.append(Spacer(1, 0.5*cm))

    # Journal des modifications (ISO 14064 — traçabilité)
    elems.append(Paragraph("Journal des modifications (ISO 14064 — Traçabilité)", S['subsec']))
    if journal:
        rows2 = [["ID Act.", "Champ modifié", "Avant", "Après", "Raison", "Date"]]
        for j in journal:
            rows2.append([
                str(j.get("activity_id", "—")),
                j.get("champ_modifie", "—")[:15],
                str(j.get("ancienne_val", "—"))[:12],
                str(j.get("nouvelle_val", "—"))[:12],
                str(j.get("raison", "—"))[:20],
                j.get("date_fmt", "—"),
            ])
        t2 = Table(rows2, colWidths=[1.5*cm, 3*cm, 2.5*cm, 2.5*cm, 4*cm, 2.5*cm])
        t2.setStyle(_ts_hdr(colors))
        elems.append(t2)
        elems.append(Paragraph(
            "Conformément à l'ISO 14064-1 §7.4, toute modification de données MRV est tracée "
            "avec horodatage, ancienne valeur, nouvelle valeur et justification. "
            "Ces entrées ne peuvent pas être supprimées (soft delete uniquement).",
            S['small']
        ))
    else:
        elems.append(Paragraph(
            "Aucune modification enregistrée. Toutes les données sont originales.", S['body']
        ))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6 — RECOMMANDATIONS LLM
# ══════════════════════════════════════════════════════════════════════════════

def _page_recommandations(elems, recs, profil, S, colors, cm,
                          Paragraph, Table, TableStyle, Spacer, HRFlowable, **_):
    elems.append(Paragraph("5. Recommandations de Réduction", S['section']))
    elems.append(Paragraph(
        "Recommandations générées par l'assistant Dr. CarbonIQ (Groq — llama-3.3-70b) "
        "basées sur les données réelles de l'entreprise et les benchmarks officiels CBAM.",
        S['small']
    ))
    elems.append(Spacer(1, 0.4*cm))

    icons = ["🎯", "⚡", "♻️", "📊", "🔋"]
    for i, rec in enumerate(recs):
        t = Table([[
            Paragraph(f"{icons[i % 5]}  {i+1}.", S['rec_num']),
            Paragraph(rec, S['body']),
        ]], colWidths=[1.5*cm, 14.5*cm])
        t.setStyle(TableStyle([
            ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f2018')),
            ('BOX',        (0, 0), (-1, -1), 0.5, colors.HexColor('#1a3828')),
            ('PADDING',    (0, 0), (-1, -1), 10),
            ('LEFTPADDING',(1, 0), (1, 0),   6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 0.2*cm))

    elems.append(Spacer(1, 0.4*cm))
    elems.append(Paragraph(
        "Ces recommandations ont valeur indicative. Toute action de réduction doit être "
        "validée par un ingénieur certifié GHG Protocol ou un auditeur accrédité ISO 14064.",
        S['small']
    ))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 7 — DÉCLARATION DE CONFORMITÉ
# ══════════════════════════════════════════════════════════════════════════════

def _page_declaration(elems, profil, conformite, now, reference,
                      S, colors, cm, Paragraph, Table, TableStyle, Spacer, HRFlowable, **_):
    elems.append(Paragraph("6. Déclaration de Conformité", S['section']))

    nom     = profil.get("nom_entreprise") or "Entreprise"
    secteur = profil.get("secteur") or "—"
    cn      = profil.get("cn_code") or "—"
    annee   = datetime.now().year

    conforme_txt = "CONFORME" if (conformite and conformite.get("conforme")) else "EN COURS D'ÉVALUATION"

    elems.append(Paragraph(
        f"Je soussigné(e), représentant légal de <b>{nom}</b>, déclare que les données "
        f"de monitoring des émissions de gaz à effet de serre présentées dans ce rapport "
        f"sont exactes, complètes et établies conformément aux méthodes de calcul définies par :",
        S['legal']
    ))

    refs = [
        ["Règlement (UE) 2023/956",   "Mécanisme d'Ajustement Carbone aux Frontières (CBAM)"],
        ["Règlement (UE) 2025/2620",  "Benchmarks officiels et méthodes de calcul CBAM"],
        ["GHG Protocol Rev. 2024",    "Norme comptable GES — Corporate Standard"],
        ["ISO 14064-1:2018",          "Quantification et rapport des émissions GES"],
    ]
    t_refs = Table(refs, colWidths=[5.5*cm, 10.5*cm])
    t_refs.setStyle(_ts_kv(colors))
    elems.append(t_refs)
    elems.append(Spacer(1, 0.4*cm))

    # Données de la déclaration
    t_decl = Table([
        ["Entreprise déclarante",    nom],
        ["Secteur CBAM",             secteur],
        ["Code NC produit",          cn],
        ["Année de rapport",         str(annee)],
        ["Statut de conformité",     conforme_txt],
        ["Référence rapport",        reference],
        ["Date de génération",       now],
        ["Statut vérification",      "En attente de vérification tierce partie"],
        ["Logiciel MRV",             "CarbonIQ v1.0 — Anthropic Claude 4.6 API"],
    ], colWidths=[5.5*cm, 10.5*cm])
    t_decl.setStyle(_ts_kv(colors))
    elems.append(t_decl)
    elems.append(Spacer(1, 0.4*cm))

    # Statut de vérification — Règlement UE 2025/2546 (régime définitif 2026)
    verif_statut = profil.get("statut_verification") or "En attente"
    is_verif     = "verif" in verif_statut.lower()
    v_bg         = colors.HexColor('#2ea043') if is_verif else colors.HexColor('#9a6700')
    t_verif = Table([[Paragraph(
        f"VERIFICATION TIERCE PARTIE (Règl. UE 2025/2546) : {verif_statut.upper()}",
        S['cover_h2']
    )]], colWidths=[16*cm])
    t_verif.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), v_bg),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('PADDING',    (0, 0), (-1, -1), 10),
    ]))
    elems.append(t_verif)
    elems.append(Paragraph(
        "Règlement (UE) 2025/2546 : à compter du 1er janvier 2026 (régime définitif), "
        "tout rapport CBAM soumis aux autorités douanières de l'UE doit être vérifié "
        "par un organisme accrédité indépendant avant dépôt.",
        S['small']
    ))
    elems.append(Spacer(1, 0.5*cm))

    # Zone signature
    elems.append(Paragraph("Signature du Responsable CBAM", S['subsec']))
    t_sig = Table([[
        Table([
            [Paragraph("Nom & Prénom :", S['small'])],
            [Paragraph("Fonction :", S['small'])],
            [Paragraph("Date : " + now[:10], S['small'])],
            [Paragraph("Cachet :", S['small'])],
            [Paragraph("\n\n", S['small'])],
        ], colWidths=[7.5*cm]),
        Table([
            [Paragraph("Visa Vérificateur :", S['small'])],
            [Paragraph("Organisme :", S['small'])],
            [Paragraph("Numéro accréditation :", S['small'])],
            [Paragraph("\n\n", S['small'])],
        ], colWidths=[7.5*cm]),
    ]], colWidths=[8*cm, 8*cm])
    t_sig.setStyle(TableStyle([
        ('BOX',     (0, 0), (0, 0), 0.5, colors.HexColor('#1a3828')),
        ('BOX',     (1, 0), (1, 0), 0.5, colors.HexColor('#1a3828')),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
    ]))
    elems.append(t_sig)

    elems.append(Spacer(1, 0.4*cm))
    elems.append(Paragraph(
        "AVERTISSEMENT : Ce rapport est généré automatiquement à partir des données saisies dans "
        "la plateforme CarbonIQ. Il ne constitue pas un rapport de vérification au sens de "
        "l'ISO 14064-3. Une vérification par un organisme accrédité est requise pour la "
        "déclaration officielle CBAM auprès des autorités douanières de l'UE.",
        S['small']
    ))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 8 — ANNEXES
# ══════════════════════════════════════════════════════════════════════════════

def _page_annexes(elems, facteurs, S, colors, cm,
                  Paragraph, Table, Spacer, HRFlowable, **_):
    elems.append(Paragraph("7. Annexes", S['section']))

    # A — Facteurs d'émission
    elems.append(Paragraph("Annexe A — Facteurs d'émission GHG Protocol (Maroc)", S['subsec']))
    if facteurs:
        rows = [["Type d'énergie", "Facteur (kg CO2/unité)", "Unité", "Scope"]]
        for f in facteurs:
            rows.append([
                f.get("energy_type", "—"),
                str(f.get("factor", "—")),
                f.get("unit", "—"),
                f"Scope {f.get('scope', '?')}",
            ])
        t = Table(rows, colWidths=[4.5*cm, 5.5*cm, 4*cm, 2*cm])
        t.setStyle(_ts_hdr(colors))
        elems.append(t)
        elems.append(Paragraph(
            "Source : Mix énergétique marocain ONEE 2024 — GHG Protocol Scope 2 Guidance.",
            S['small']
        ))
    elems.append(Spacer(1, 0.5*cm))

    # B — Benchmarks CBAM par secteur
    elems.append(Paragraph("Annexe B — Benchmarks CBAM officiels par secteur", S['subsec']))
    bmg_rows = [["Secteur", "Colonne", "Émissions indirectes", "Routes disponibles"]]
    for key, info in CBAM_REFERENCE.items():
        routes = ", ".join(list(info.get("routes", {}).keys())[:4])
        if len(info.get("routes", {})) > 4:
            routes += "..."
        bmg_rows.append([
            f"{key} ({info.get('fr', '')})",
            f"Colonne {info.get('colonne_obligatoire', '?')}",
            info.get("emissions_indirectes", "—"),
            routes or "Benchmark unique",
        ])
    t2 = Table(bmg_rows, colWidths=[5*cm, 2.5*cm, 4*cm, 4.5*cm])
    t2.setStyle(_ts_hdr(colors))
    elems.append(t2)
    elems.append(Paragraph(
        "Source : Règlement d'exécution (UE) 2025/2620, Annexe III — 570 produits couverts.",
        S['small']
    ))
    elems.append(Spacer(1, 0.5*cm))

    # C — Glossaire
    elems.append(Paragraph("Annexe C — Glossaire", S['subsec']))
    rows3 = [["Terme", "Définition"]]
    for terme, defn in GLOSSAIRE:
        rows3.append([terme, defn])
    t3 = Table(rows3, colWidths=[3.5*cm, 12.5*cm])
    t3.setStyle(_ts_hdr(colors))
    elems.append(t3)


# ══════════════════════════════════════════════════════════════════════════════
# BUILDER 2026 — PAYLOAD POUR cbam_2026.py (9 sections définitives)
# ══════════════════════════════════════════════════════════════════════════════

def _build_payload_2026(req, profil, par_scope, par_source, activites, journal, conformite, recs):
    """Construit le payload attendu par generate_cbam_declaration_report (cbam_2026.py)."""
    from datetime import date as _date

    annee     = (req.annee if req and req.annee else None) or datetime.now().year

    _SECTEUR_V2 = {
        "Acier/Fer": "steel", "Aluminium": "aluminium", "Ciment": "cement",
        "Engrais": "fertilizers", "Hydrogène": "hydrogen",
    }
    secteur_v2 = _SECTEUR_V2.get(profil.get("secteur", ""), "")

    s1_t  = par_scope.get(1, 0.0) / 1000
    s2_t  = par_scope.get(2, 0.0) / 1000
    prod_t = float(profil.get("production_annuelle_tonnes") or 0)

    # Scope 1 / Scope 2 breakdown depuis par_source
    s1_breakdown: dict = {}
    s2_breakdown: dict = {}
    for s in par_source:
        src = s.get("source", "").lower()
        kg  = float(s.get("co2_kg", 0))
        if src == "electricity":
            s2_breakdown["electricity"] = round(kg / 1000, 3)
        else:
            s1_breakdown[src] = round(kg / 1000, 3)
    if not s1_breakdown:
        s1_breakdown = {"combustion": round(s1_t, 3)}
    if not s2_breakdown:
        s2_breakdown = {"electricity": round(s2_t, 3)}

    benchmark_val = conformite.get("benchmark", 0.0) if (conformite and conformite.get("valide")) else 0.0

    # Vérificateur
    verif_status = "verified" if (req and req.verifier_nom and req.verifier_accreditation) else "pending"
    verif_name   = (req.verifier_nom if req else "") or "—"
    verif_id     = (req.verifier_accreditation if req else "") or "—"

    # Audit trail : journal → format cbam_2026
    audit_trail = [
        {
            "date":   j.get("date_fmt", ""),
            "field":  j.get("champ_modifie", "—"),
            "old":    j.get("ancienne_val", "—"),
            "new":    j.get("nouvelle_val", "—"),
            "reason": j.get("raison", "—"),
        }
        for j in journal
    ]

    report_id = f"CIQ-{annee}-AN-{datetime.now().strftime('%H%M%S')}"

    return {
        "report_id":  report_id,
        "issue_date": _date.today(),
        "year":       annee,
        "installation": {
            "legal_name":             profil.get("nom_entreprise") or (req.nom_installation if req else "") or "—",
            "country":                "MA",
            "eori":                   (req.eori if req else "") or "—",
            "address":                (req.ville_installation if req else "") or "Maroc",
            "sector":                 secteur_v2,
            "cn_code":                profil.get("cn_code") or "—",
            "production_route":       profil.get("route_production") or "—",
            "production_tonnes_year": prod_t,
            "o3ci_registration":      (req.o3ci_id if req else "") or "PENDING-2026",
        },
        "verification": {
            "status":          verif_status,
            "verifier_name":   verif_name,
            "verifier_id":     verif_id,
            "site_visit_date": None,
        },
        "emissions": {
            "scope1_t_co2":       round(s1_t, 3),
            "scope2_t_co2":       round(s2_t, 3),
            "scope1_breakdown":   s1_breakdown,
            "scope2_breakdown":   s2_breakdown,
            "tier_level":         2,
            "measurement_method": (req.methode_determination if req else "") or "measured",
        },
        "benchmark": {
            "benchmark_t_co2_per_t":    round(benchmark_val, 4),
            "default_value_with_markup": round(benchmark_val * 1.20, 4),
            "markup_pct":               20.0,
        },
        "commodities": [{
            "cn_code":                profil.get("cn_code") or "—",
            "description":            profil.get("secteur") or "—",
            "quantity_exported_tonnes": (req.quantite_importee if req else 0) or prod_t,
            "quantity_imported_eu":   (req.quantite_importee if req else 0),
            "country_destination":    "EU",
        }],
        "activities":  activites,
        "audit_trail": audit_trail,
        "recommendations": [
            {"tag": "PRESCRIPTION", "text": r, "regulation_ref": "GHG Protocol Rev. 2024"}
            for r in recs
        ],
    }


@router.post("/generate-report/v2")
def generer_rapport_v2(req: RapportRequest = None):
    """Génère le rapport PDF CBAM 2026 définitif — 9 sections officielles (cbam_2026.py).
    SHA-256 + QR code + bilingue FR/EN."""

    profil, totaux, par_scope, par_source, _, activites, journal, _ = _get_donnees()

    total_kg = float(totaux.get("total_co2_kg") or 0)
    s1_kg    = par_scope.get(1, 0)
    s2_kg    = par_scope.get(2, 0)

    conformite = None
    if profil.get("production_annuelle_tonnes"):
        mot_cle  = _SECTEUR_MOT_CLE.get(profil.get("secteur", ""), "")
        cbam_key = _SECTEUR_CBAM_KEY.get(profil.get("secteur", ""), "")
        colonne  = get_colonne_obligatoire(cbam_key) if cbam_key else "A"
        co2_cbam = s1_kg if colonne == "A" else total_kg
        conformite = calculer_conformite(
            total_co2_kg      = co2_cbam,
            production_tonnes = profil["production_annuelle_tonnes"],
            mot_cle           = mot_cle or None,
            cn_code           = profil.get("cn_code") or None,
            secteur           = cbam_key or None,
            route             = profil.get("route_production") or None,
        )

    recs = _generer_recommandations(total_kg / 1000, s1_kg / 1000, s2_kg / 1000, conformite, profil)

    lang    = (req.lang if req and req.lang else "fr").lower()
    payload = _build_payload_2026(req, profil, par_scope, par_source, activites, journal, conformite, recs)

    pdf_bytes = generate_cbam_declaration_report(payload, lang=lang)

    nom    = profil.get("nom_entreprise") or "Entreprise"
    annee  = (req.annee if req and req.annee else None) or datetime.now().year
    filename = f"CarbonIQ_CBAM_2026_{nom.replace(' ', '_')}_{annee}.pdf"

    return Response(
        content    = pdf_bytes,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL (v1 — thème dark, 8 sections)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/generate-report")
def generer_rapport_pdf(req: RapportRequest = None):
    """Génère le rapport PDF CBAM officiel en 8 sections (7 numérotées + couverture)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable, PageBreak
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="reportlab non installé — exécutez : pip install reportlab"
        )

    # ── Données ──────────────────────────────────────
    profil, totaux, par_scope, par_source, par_mois, activites, journal, facteurs = _get_donnees()

    total_kg = float(totaux.get("total_co2_kg") or 0)
    s1_kg    = par_scope.get(1, 0)
    s2_kg    = par_scope.get(2, 0)
    nb_act   = int(totaux.get("nb_activites") or 0)

    # Conformité CBAM
    conformite = None
    if profil.get("production_annuelle_tonnes"):
        mot_cle  = _SECTEUR_MOT_CLE.get(profil.get("secteur", ""), "")
        cbam_key = _SECTEUR_CBAM_KEY.get(profil.get("secteur", ""), "")
        colonne  = get_colonne_obligatoire(cbam_key) if cbam_key else "A"
        co2_cbam = s1_kg if colonne == "A" else total_kg
        conformite = calculer_conformite(
            total_co2_kg      = co2_cbam,
            production_tonnes = profil["production_annuelle_tonnes"],
            mot_cle           = mot_cle or None,
            cn_code           = profil.get("cn_code") or None,
            secteur           = cbam_key or None,
            route             = profil.get("route_production") or None,
        )

    # Recommandations LLM
    recs = _generer_recommandations(
        total_kg / 1000, s1_kg / 1000, s2_kg / 1000, conformite, profil
    )

    # Métadonnées
    now       = datetime.now().strftime('%d/%m/%Y à %Hh%M')
    reference = f"CIQ-{datetime.now().strftime('%Y%m%d-%H%M')}"
    nom       = profil.get("nom_entreprise") or "Entreprise"

    # Styles
    S = _styles(colors, cm)

    # Helpers partiels
    kw = dict(
        req=req,
        S=S, colors=colors, cm=cm,
        Paragraph=Paragraph, Table=Table, TableStyle=TableStyle,
        Spacer=Spacer, HRFlowable=HRFlowable,
    )

    # ── Construction du PDF ──────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.8*cm, bottomMargin=2*cm,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        title=f"Rapport CBAM — {nom}",
        author="CarbonIQ v1.0",
    )

    elems = []

    # PAGE 1 — Couverture
    _page_couverture(elems, profil, now, reference, **kw)
    elems.append(PageBreak())

    # PAGE 2 — Identification
    _page_identification(elems, profil, nb_act, **kw)
    elems.append(PageBreak())

    # PAGE 2bis — Goods Imported (Section 2 CBAM)
    _page_marchandises(elems, profil, **kw)
    elems.append(PageBreak())

    # PAGE 3 — Bilan émissions + graphiques
    _page_bilan(elems, totaux, par_scope, par_source, par_mois, facteurs, **kw)
    elems.append(PageBreak())

    # PAGE 4 — Conformité CBAM + jauge
    _page_conformite(elems, conformite, profil, par_scope, **kw)
    elems.append(PageBreak())

    # PAGE 5 — Monitoring détaillé + journal ISO 14064
    _page_monitoring(elems, activites, journal, **kw)
    elems.append(PageBreak())

    # PAGE 6 — Recommandations LLM
    _page_recommandations(elems, recs, profil, **kw)
    elems.append(PageBreak())

    # PAGE 7 — Déclaration de conformité
    _page_declaration(elems, profil, conformite, now, reference, **kw)
    elems.append(PageBreak())

    # PAGE 8 — Annexes
    _page_annexes(elems, facteurs, **kw)

    # Pied de page commun (dernière section)
    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#1a3828')))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(Paragraph(
        f"CarbonIQ v1.0  ·  Réf. {reference}  ·  {now}  ·  "
        "Conforme GHG Protocol Rev. 2024 & Règlement UE 2025/2620",
        S['footer']
    ))

    doc.build(elems)
    buffer.seek(0)

    nom_fichier = (
        f"CarbonIQ_CBAM_{nom.replace(' ', '_')}"
        f"_{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'}
    )
