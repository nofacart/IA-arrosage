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
        "tomate": {"seuil_jours": 2},
        "courgette": {"seuil_jours": 2},
        "haricot vert": {"seuil_jours": 3},
        "melon": {"seuil_jours": 3},
        "fraise": {"seuil_jours": 2},
        "aromatiques": {"seuil_jours": 5},
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

def color_band(arroser):
    return "background-color: #FFA500;" if arroser else "background-color: #87CEEB;"

st.set_page_config(page_title="🌿 Arrosage potager", layout="wide")
st.title("🌿 Aide à l’arrosage du potager")

try:
    df = recuperer_meteo()
    plantes = charger_plantes()
    today = pd.to_datetime(datetime.now().date())
    df["jour"] = df["date"].dt.strftime("%d/%m")

    # Section météo résumé
    st.subheader("📊 Données météo")
    df_past = df[df["date"] < today]
    pluie_passe = df_past["pluie"].sum()
    jours_chauds = (df_past["temp_max"] >= 28).sum()
    evapo_passe = df_past["evapo"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Pluie (7 jours passés)", f"{pluie_passe:.1f} mm")
    col2.metric("Jours chauds (≥28°C)", f"{jours_chauds}")
    col3.metric("Évapotranspiration", f"{evapo_passe:.1f} mm")

    # Tableau météo avec jour actuel en gras
    st.markdown("### 📅 Tableau météo")
    df_display = df[["jour", "temp_max", "pluie", "evapo", "radiation", "vent"]].copy()
    df_display.columns = ["Jour", "Temp (°C)", "Pluie (mm)", "Évapo", "Radiation", "Vent (km/h)"]

    def highlight_today(row):
        return ['font-weight: bold; background-color: #d0f0ff' if row["Jour"] == today.strftime("%d/%m") else '' for _ in row]

    st.dataframe(df_display.style.apply(highlight_today, axis=1), height=350)

    # Graphique temperature + pluie
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

    # Slider jours depuis dernier arrosage
    st.subheader("🧮 Indiquez depuis combien de jours vous avez arrosé")
    jours_depuis = st.slider("Jours depuis le dernier arrosage", 0, 14, 3)

    # Calcul recommandations
    st.markdown("### 🌱 Recommandations personnalisées")
    table_data = []
    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", 3)
        nom = plante.capitalize()

        if jours_depuis <= seuil:
            besoin = False
        else:
            date_depuis = today - pd.Timedelta(days=jours_depuis - seuil)
            df_depuis = df[df.date >= date_depuis]
            pluie = df_depuis["pluie"].sum()
            jours_chauds_loc = (df_depuis["temp_max"] >= 28).sum()
            evapo = df_depuis["evapo"].sum()
            besoin = pluie < 5 and (jours_chauds_loc >= 1 or evapo >= 10)

        couleur = "🟧" if besoin else "🟦"
        msg = "Arroser" if besoin else "Pas besoin"
        table_data.append({
            "Plante": nom,
            "Recommandation": msg,
            "Couleur": couleur,
            "Infos": f"Arrosé il y a {jours_depuis} jours, seuil {seuil}"
        })

    # Affichage dynamique avec couleurs orange / bleu
    for ligne in table_data:
        color = "#FFA500" if ligne["Couleur"] == "🟧" else "#87CEEB"
        st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                    f"**{ligne['Plante']}** : {ligne['Recommandation']} ({ligne['Infos']})"
                    f"</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ Erreur : {e}")
