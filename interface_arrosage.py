import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === BASE_DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🌍 CONFIG
LAT, LON = 43.66528, 1.3775  # Beauzelle
TIMEZONE = "Europe/Paris"
CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json")
]

def charger_plantes():
    for path in CANDIDATE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {
        "tomate": {"kc": 1.15},
        "courgette": {"kc": 1.05},
        "haricot vert": {"kc": 1.0},
        "melon": {"kc": 1.05},
        "fraise": {"kc": 1.05},
        "aromatiques": {"kc": 0.7}
    }

def recuperer_meteo():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max,et0_fao_evapotranspiration",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": TIMEZONE
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "temp_max": d["temperature_2m_max"],
        "pluie": d["precipitation_sum"],
        "radiation": d.get("shortwave_radiation_sum", [None]*len(d["time"])),
        "vent": d.get("windspeed_10m_max", [None]*len(d["time"])),
        "evapo": d.get("et0_fao_evapotranspiration", [None]*len(d["time"]))
    })

# === APP START ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="wide")
st.title("🌿 Aide à l’arrosage du potager")

try:
    df = recuperer_meteo()
    plantes = charger_plantes()
    today = pd.to_datetime(datetime.now().date())
    df["jour"] = df["date"].dt.strftime("%d/%m")

    # --- Résumé météo ---
    st.subheader("📊 Données météo récentes")
    df_past = df[df["date"] < today]
    pluie_passe = df_past["pluie"].sum()
    jours_chauds = (df_past["temp_max"] >= 28).sum()
    evapo_passe = df_past["evapo"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Pluie (7 derniers jours)", f"{pluie_passe:.1f} mm")
    col2.metric("Jours ≥28°C", f"{jours_chauds}")
    col3.metric("Évapotranspiration", f"{evapo_passe:.1f} mm")

    df_display = df[["jour", "temp_max", "pluie", "evapo", "radiation", "vent"]].copy()
    df_display.columns = ["Jour", "Temp (°C)", "Pluie (mm)", "Évapo", "Radiation", "Vent (km/h)"]

    st.markdown("### 📅 Météo en cartes")

    for idx, row in df_display.iterrows():
        jour = row["Jour"]
        temp = row["Temp (°C)"]
        pluie = row["Pluie (mm)"]
        evapo = row["Évapo"]
        radiation = row["Radiation"]
        vent = row["Vent (km/h)"]

        is_today = (jour == today.strftime("%d/%m"))
        card_style = (
            "background-color: #d0f0ff; font-weight: bold; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"
            if is_today else
            "background-color: #f9f9f9;"
        )

        st.markdown(f"""
        <div style="
            {card_style}
            border-radius: 10px;
            padding: 12px 20px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        ">
            <div style="flex: 1; min-width: 70px;">📅 <b>{jour}</b></div>
            <div style="flex: 1; color: crimson; min-width: 90px;">🌡️ {temp} °C</div>
            <div style="flex: 1; color: royalblue; min-width: 90px;">🌧️ {pluie:.1f} mm</div>
            <div style="flex: 1; min-width: 90px;">💧 {evapo:.1f}</div>
            <div style="flex: 1; min-width: 90px;">☀️ {int(radiation) if radiation else '-'} W/m²</div>
            <div style="flex: 1; min-width: 90px;">🌬️ {int(vent) if vent else '-'} km/h</div>
        </div>
        """, unsafe_allow_html=True)



    # --- Graphique température + pluie ---
    st.markdown("### 📈 Température & Pluie")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=df["jour"], y=df["temp_max"], name="Température (°C)",
        mode="lines+markers", line=dict(color="crimson")
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["jour"], y=df["pluie"], name="Pluie (mm)",
        marker_color="royalblue", opacity=0.6
    ), secondary_y=True)
    fig.update_layout(
        height=400,
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=30, b=30),
        hovermode="x unified"
    )
    fig.update_yaxes(title_text="🌡️ Température (°C)", secondary_y=False)
    fig.update_yaxes(title_text="🌧️ Pluie (mm)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    # --- Paramètres utilisateur ---
    st.subheader("🧮 Paramètres de votre jardin")
    type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"])
    paillage = st.checkbox("Présence de paillage")
    jours_depuis = st.slider("Jours depuis le dernier arrosage :", 0, 14, 3)

    facteur_sol = {
        "Sableux": 1.3,
        "Limoneux": 1.0,
        "Argileux": 0.9
    }.get(type_sol, 1.0)
    facteur_paillage = 0.7 if paillage else 1.0

    # --- Seuil déficit dynamique selon le type de sol ---
    SEUILS_DEFICIT_SOL = {
        "Sableux": 10,
        "Limoneux": 20,
        "Argileux": 30
    }
    SEUIL_DEFICIT = SEUILS_DEFICIT_SOL.get(type_sol, 20)
    st.caption(f"💧 Seuil de déficit pour arrosage ({type_sol.lower()}) : {SEUIL_DEFICIT} mm")

    # --- Alertes météo intelligentes ---
    df_futur = df[df["date"] > today]
    jours_chauds_a_venir = (df_futur["temp_max"] >= 30).sum()
    pluie_prochaine_48h = df_futur.head(2)["pluie"].sum()

    if jours_chauds_a_venir >= 2:
        st.warning(f"🔥 Attention : {jours_chauds_a_venir} jours à venir avec ≥30°C. Anticipez un éventuel stress hydrique.")
    if pluie_prochaine_48h >= 10:
        st.info(f"🌧️ Bonne nouvelle : {pluie_prochaine_48h:.1f} mm de pluie attendus dans les 48h. Vous pouvez peut-être attendre avant d’arroser.")

    # --- Calcul recommandations ---
    st.markdown("## 🌱 Recommandations personnalisées")
    table_data = []

    for plante, infos in plantes.items():
        kc = infos.get("kc", 1.0)
        nom = plante.capitalize()

        date_depuis = today - pd.Timedelta(days=jours_depuis)
        date_jusqua = today + pd.Timedelta(days=3)
        df_analyse = df[(df["date"] >= date_depuis) & (df["date"] <= date_jusqua)]

        pluie_totale = df_analyse["pluie"].sum()
        et0_total = df_analyse["evapo"].sum()
        besoin_total = et0_total * kc * facteur_sol * facteur_paillage
        bilan = pluie_totale - besoin_total
        deficit = -bilan if bilan < 0 else 0

        # Projection pluie dans les 3 prochains jours
        df_prevision = df_analyse[df_analyse["date"] > today]
        pluie_prochaine = df_prevision["pluie"].sum()

        # Détermination besoin d'arrosage
        if deficit == 0:
            besoin = False
            infos_bilan = f"✅ Excédent : {bilan:.1f} mm"
        elif deficit <= SEUIL_DEFICIT:
            besoin = False
            infos_bilan = f"🤏 Déficit léger : {deficit:.1f} mm"
        else:
            if pluie_prochaine >= deficit:
                besoin = False
                infos_bilan = f"🌧️ Pluie prévue ({pluie_prochaine:.1f} mm) compensera"
            else:
                besoin = True
                infos_bilan = f"💧 Déficit : {deficit:.1f} mm"

        couleur = "🟧" if besoin else "🟦"
        msg = "Arroser" if besoin else "Pas besoin"

        table_data.append({
            "Plante": nom,
            "Recommandation": msg,
            "Couleur": couleur,
            "Détail": infos_bilan
        })

    # --- Affichage recommandations ---
    for ligne in table_data:
        color = "#FFA500" if ligne["Couleur"] == "🟧" else "#87CEEB"
        st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                    f"<b>{ligne['Plante']}</b> : {ligne['Recommandation']} – {ligne['Détail']}"
                    f"</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ Erreur : {e}")
