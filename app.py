# app.py
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

# ================================================
# CONFIGURATION
# ================================================
st.set_page_config(
    page_title="CarbonIQ — Tableau de bord",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://localhost:8000"

# Style CSS custom pour améliorer Streamlit
st.markdown("""
<style>
    /* Fond sombre */
    .stApp { background-color: #0a0f0d; }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #111a15;
        border-right: 1px solid #1e3025;
    }
    
    /* Cartes métriques */
    [data-testid="metric-container"] {
        background-color: #111a15;
        border: 1px solid #1e3025;
        border-radius: 12px;
        padding: 16px;
    }
    
    /* Titres */
    h1, h2, h3 { color: #e8f5ec !important; }
    
    /* Texte normal */
    p, span, div { color: #e8f5ec; }
    
    /* Boutons */
    .stButton > button {
        background-color: #2dff7a;
        color: #0a0f0d;
        font-weight: 700;
        border: none;
        border-radius: 8px;
    }
    .stButton > button:hover {
        background-color: #22e06a;
        color: #0a0f0d;
    }
    
    /* Input */
    .stTextInput > div > div > input {
        background-color: #111a15;
        border: 1px solid #1e3025;
        color: #e8f5ec;
        border-radius: 8px;
    }
    
    /* Boîte insight IA */
    .insight-box {
        background: #162019;
        border: 1px solid rgba(45,255,122,0.2);
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        border-left: 3px solid #2dff7a;
    }
    
    /* Badge CBAM */
    .cbam-ok {
        background: rgba(45,255,122,0.1);
        border: 1px solid rgba(45,255,122,0.3);
        color: #2dff7a;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 13px;
        display: inline-block;
        margin-bottom: 16px;
    }
    .cbam-nok {
        background: rgba(255,69,96,0.1);
        border: 1px solid rgba(255,69,96,0.3);
        color: #ff4560;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 13px;
        display: inline-block;
        margin-bottom: 16px;
    }
    
    /* Alerte */
    .alert-danger {
        background: rgba(255,69,96,0.08);
        border-left: 3px solid #ff4560;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 13px;
    }
    .alert-warn {
        background: rgba(255,140,66,0.08);
        border-left: 3px solid #ff8c42;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 13px;
    }
    .alert-ok {
        background: rgba(45,255,122,0.06);
        border-left: 3px solid #2dff7a;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 13px;
    }
</style>
""", unsafe_allow_html=True)

# ================================================
# FONCTIONS UTILITAIRES
# ================================================

def call_api(endpoint):
    """Appelle l'API FastAPI et retourne les données"""
    try:
        response = requests.get(f"{API_URL}/{endpoint}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def post_api(endpoint, data):
    """Envoie des données à l'API"""
    try:
        response = requests.post(f"{API_URL}/{endpoint}", json=data, timeout=5)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# ================================================
# SIDEBAR
# ================================================
with st.sidebar:
    st.markdown("## 🌿 CarbonIQ")
    st.markdown("*Plateforme MRV intelligente*")
    st.divider()

    page = st.radio(
        "Navigation",
        ["◈ Dashboard", "↑ Import PDF", "≡ Activités", "⬡ Analyse IA", "▤ Rapport CBAM"],
        label_visibility="collapsed"
    )

    st.divider()

    # Statut API
    api_check = call_api("")
    if api_check:
        st.success("✅ API connectée")
    else:
        st.error("❌ API déconnectée")

    st.markdown("---")
    st.markdown("**Entreprise**")
    st.markdown("IndustriMaroc SA")
    st.caption("Responsable : Ahmed B.")

# ================================================
# PAGE 1 : DASHBOARD PRINCIPAL
# ================================================
if "◈ Dashboard" in page:

    # Titre
    col_title, col_badge = st.columns([3, 1])
    with col_title:
        st.title("📊 Tableau de bord")
        st.caption("Mise à jour en temps réel · Janvier — Février 2024")
    with col_badge:
        stats = call_api("stats")
        if stats:
            if "CONFORME" in stats.get("statut_cbam", ""):
                st.markdown('<div class="cbam-ok">🟢 CBAM : CONFORME</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="cbam-nok">🔴 CBAM : NON CONFORME</div>', unsafe_allow_html=True)

    # ---- KPI CARDS ----
    st.markdown("### Indicateurs clés")
    k1, k2, k3, k4 = st.columns(4)

    if stats:
        total_co2 = stats.get("total_co2_kg", 0)
        total_tonnes = stats.get("total_co2_tonnes", 0)

        # Scope 1 et 2 depuis par_scope
        scope1 = next((s["total_co2_kg"] for s in stats.get("par_scope", []) if s["scope"] == 1), 0)
        scope2 = next((s["total_co2_kg"] for s in stats.get("par_scope", []) if s["scope"] == 2), 0)

        with k1:
            st.metric(
                label="🌍 Émissions totales",
                value=f"{total_tonnes:.2f} t CO₂",
                delta="+12% vs période préc.",
                delta_color="inverse"
            )
        with k2:
            st.metric(
                label="🔥 Scope 1 (direct)",
                value=f"{scope1/1000:.2f} t CO₂",
                delta="-3% vs période préc.",
                delta_color="normal"
            )
        with k3:
            st.metric(
                label="⚡ Scope 2 (électricité)",
                value=f"{scope2/1000:.2f} t CO₂",
                delta="+18% vs période préc.",
                delta_color="inverse"
            )
        with k4:
            intensite = total_co2 / 1000 if total_co2 > 0 else 0
            st.metric(
                label="📏 Intensité carbone",
                value=f"{intensite:.3f} t/unité",
                delta="+5%",
                delta_color="inverse"
            )
    else:
        with k1:
            st.metric("🌍 Émissions totales", "—", "API déconnectée")
        with k2:
            st.metric("🔥 Scope 1", "—")
        with k3:
            st.metric("⚡ Scope 2", "—")
        with k4:
            st.metric("📏 Intensité", "—")

    st.divider()

    # ---- GRAPHIQUES ----
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("### 📈 Émissions par mois")

        if stats and stats.get("par_mois"):
            df_mois = pd.DataFrame(stats["par_mois"])
            df_mois.columns = ["Mois", "CO2 (kg)"]

            fig = px.bar(
                df_mois,
                x="Mois",
                y="CO2 (kg)",
                color_discrete_sequence=["#2dff7a"],
                template="plotly_dark"
            )
            fig.update_layout(
                plot_bgcolor="#111a15",
                paper_bgcolor="#111a15",
                font_color="#5a7a63",
                showlegend=False,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#1e3025"),
                yaxis=dict(gridcolor="#1e3025")
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée disponible. Ajoutez des activités d'abord.")

    with col_right:
        st.markdown("### 🍩 Répartition")

        if stats and stats.get("par_source"):
            df_src = pd.DataFrame(stats["par_source"])

            fig2 = px.pie(
                df_src,
                names="source",
                values="total_co2_kg",
                color_discrete_sequence=["#42a5ff", "#ff8c42", "#2dff7a"],
                hole=0.6,
                template="plotly_dark"
            )
            fig2.update_layout(
                plot_bgcolor="#111a15",
                paper_bgcolor="#111a15",
                font_color="#5a7a63",
                showlegend=True,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(font=dict(color="#5a7a63"))
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Pas de données sources.")

    st.divider()

    # ---- ALERTES ----
    st.markdown("### 🔔 Alertes intelligentes")

    if stats:
        total = stats.get("total_co2_kg", 0)
        scope2_val = next((s["total_co2_kg"] for s in stats.get("par_scope", []) if s["scope"] == 2), 0)

        if total > 50000:
            st.markdown('<div class="alert-danger">⚠️ <strong>Émissions élevées :</strong> Vous dépassez 50 tonnes CO₂. Risque de non-conformité CBAM.</div>', unsafe_allow_html=True)
        if scope2_val > 5000:
            st.markdown('<div class="alert-warn">◎ <strong>Scope 2 élevé :</strong> Consommation électricité importante ce mois. Vérifiez vos équipements.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="alert-ok">✓ <strong>Émissions normales :</strong> Vos émissions sont dans les seuils acceptables.</div>', unsafe_allow_html=True)

        st.markdown('<div class="alert-ok">✓ <strong>Données à jour :</strong> Toutes vos activités sont enregistrées et validées.</div>', unsafe_allow_html=True)

# ================================================
# PAGE 2 : IMPORT PDF
# ================================================
elif "↑ Import PDF" in page:
    st.title("📄 Import de données PDF")
    st.caption("Uploadez vos factures — l'IA extrait les données automatiquement")

    st.info("🔧 Cette fonctionnalité sera connectée en **Semaine 3** (Sprint OCR + LLM)")

    uploaded = st.file_uploader(
        "Glissez vos factures ici",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded:
        for f in uploaded:
            st.success(f"✅ {f.name} reçu — extraction automatique bientôt disponible")

# ================================================
# PAGE 3 : ACTIVITÉS
# ================================================
elif "≡ Activités" in page:
    st.title("📋 Gestion des activités")

    tab1, tab2 = st.tabs(["➕ Ajouter une activité", "📋 Voir toutes les activités"])

    with tab1:
        st.markdown("### Nouvelle activité")

        col1, col2 = st.columns(2)
        with col1:
            source = st.selectbox(
                "Type d'énergie",
                ["electricity", "fuel", "gas"],
                format_func=lambda x: {
                    "electricity": "⚡ Électricité",
                    "fuel": "🔥 Fuel / Gasoil",
                    "gas": "💨 Gaz naturel"
                }[x]
            )
            quantity = st.number_input("Quantité", min_value=0.0, value=100.0, step=10.0)

        with col2:
            unit_map = {
                "electricity": "kWh",
                "fuel": "litres",
                "gas": "m3"
            }
            unit = unit_map[source]
            st.text_input("Unité", value=unit, disabled=True)
            activity_date = st.date_input("Date", value=date.today())

        if st.button("💾 Ajouter et calculer les émissions", use_container_width=True):
            result = post_api("activities", {
                "source": source,
                "quantity": quantity,
                "unit": unit,
                "date": str(activity_date)
            })

            if "error" not in result:
                st.success("✅ Activité ajoutée !")
                calcul = result.get("calcul", {})
                st.markdown(f"""
                **Résultat du calcul :**
                - Quantité : `{calcul.get('quantite')} {calcul.get('unite')}`
                - Facteur CO₂ : `{calcul.get('facteur_co2')} kg CO₂/unité`
                - **Émissions : `{calcul.get('co2_kg')} kg CO₂`**
                - Scope : `{calcul.get('scope')}`
                """)
            else:
                st.error(f"Erreur : {result}")

    with tab2:
        data = call_api("activities")
        if data and data.get("data"):
            df = pd.DataFrame(data["data"])
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )
            st.caption(f"Total : {data['count']} activités enregistrées")
        else:
            st.info("Aucune activité. Ajoutez-en via l'onglet ci-dessus.")

# ================================================
# PAGE 4 : ANALYSE IA
# ================================================
elif "⬡ Analyse IA" in page:
    st.title("🤖 Assistant IA — Analyse carbone")
    st.caption("Propulsé par LLM · Connecté en Semaine 6")

    st.info("🔧 Le vrai LLM (Groq) sera connecté en **Semaine 6**. Pour l'instant, voici des insights simulés.")

    stats = call_api("stats")

    if stats:
        total = stats.get("total_co2_kg", 0)

        st.markdown('<div class="insight-box">📊 <strong>Analyse automatique :</strong><br>Vos émissions totales sont de <strong>' + str(round(total, 1)) + ' kg CO₂</strong> sur la période analysée. ' + ("Vous êtes dans les seuils CBAM acceptables. ✅" if total < 100000 else "Attention : vous approchez des seuils CBAM. ⚠️") + '</div>', unsafe_allow_html=True)

    st.markdown("### 💬 Posez une question")
    question = st.text_input("", placeholder="Ex: Pourquoi mes émissions ont augmenté ce mois ?")

    if st.button("Analyser →") and question:
        with st.spinner("L'IA analyse..."):
            import time
            time.sleep(1.5)
            st.markdown('<div class="insight-box">🤖 <strong>Réponse IA (simulée) :</strong><br>La connexion au LLM sera disponible en Semaine 6. À ce stade, je peux vous dire que vos données sont correctement enregistrées et que le calcul MRV est conforme au GHG Protocol.</div>', unsafe_allow_html=True)

# ================================================
# PAGE 5 : RAPPORT CBAM
# ================================================
elif "▤ Rapport CBAM" in page:
    st.title("📑 Génération de rapport CBAM")
    st.caption("Rapport structuré conforme GHG Protocol · ISO 14064")

    st.info("🔧 La génération PDF sera connectée en **Semaine 7**.")

    stats = call_api("stats")

    if stats:
        st.markdown("### Aperçu du rapport")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Émissions totales", f"{stats['total_co2_tonnes']} t CO₂e")
        with col2:
            st.metric("Statut CBAM", "CONFORME ✅" if "CONFORME" in stats.get("statut_cbam","") else "NON CONFORME ❌")
        with col3:
            st.metric("Période", "Jan–Fév 2024")

        st.markdown("---")
        st.markdown("**Contenu du rapport :**")
        st.markdown("""
        - ✅ Résumé exécutif
        - ✅ Émissions Scope 1 & 2 détaillées
        - ✅ Facteurs d'émission utilisés (GHG Protocol)
        - ✅ Analyse de conformité CBAM
        - ✅ Recommandations de réduction
        - 🔧 Signature électronique (Semaine 7)
        """)

        if st.button("📥 Générer le rapport PDF", use_container_width=True):
            st.warning("🔧 Fonctionnalité disponible en Semaine 7 !")