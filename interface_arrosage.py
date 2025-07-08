import streamlit as st
import os
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- PARAMÈTRES FIXES ---
RAPPORT_FILE = "rapport_arrosage_openmeteo.txt"
LAT, LON = 43.66528, 1.3775  # Beauzelle


# --- Fonction : Récupération données météo (7j passés + 7j prévus) ---
@st.cache_data(ttl=3600)
def charger_donnees_meteo():
    base_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max,precipitation_sum",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": "Europe/Paris"
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame({
            "date": pd.to_datetime(data["daily"]["time"]),
            "temp_max": data["daily"]["temperature_2m_max"],
            "pluie": data["daily"]["precipitation_sum"]
        })
        return df
    else:
        st.error(f"Erreur lors du chargement météo : {response.status_code}")
        return pd.DataFrame()


# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Assistant Arrosage", page_icon="🌿")
st.title("🌿 Assistant d’Arrosage du Potager")
st.markdown("Suivi météo automatisé & recommandations d’arrosage.")

# --- Rapport météo/arrosage ---
st.subheader("📝 Rapport météo et recommandation")
if os.path.exists(RAPPORT_FILE):
    with open(RAPPORT_FILE, "r", encoding="utf-8") as f:
        rapport = f.read()
    st.text(rapport)
else:
    st.warning("Aucun rapport trouvé. Veuillez exécuter le script d’arrosage.")

# --- Graphique météo (Open-Meteo) ---
st.subheader("📊 Évolution météo (14 jours)")
df_meteo = charger_donnees_meteo()

if not df_meteo.empty:
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_meteo["date"],
        y=df_meteo["pluie"],
        name="Pluie (mm)",
        marker_color='skyblue',
        yaxis="y"
    ))

    fig.add_trace(go.Scatter(
        x=df_meteo["date"],
        y=df_meteo["temp_max"],
        name="Température max (°C)",
        mode="lines+markers",
        line=dict(color='tomato', width=2),
        yaxis="y2"
    ))

    fig.update_layout(
        title="Température & Précipitations (7 jours passés + 7 jours prévus)",
        xaxis_title="Date",
        yaxis=dict(title="Pluie (mm)", side="left"),
        yaxis2=dict(title="Température max (°C)", overlaying="y", side="right"),
        legend=dict(x=0.01, y=1.2, orientation="h"),
        margin=dict(t=50, b=20),
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Chargement des données météo en attente...")

# --- Footer ---
st.markdown("---")
st.markdown("Développé avec ❤️ pour le potager de Beauzelle 🌻")
