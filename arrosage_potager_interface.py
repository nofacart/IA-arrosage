import requests
import pandas as pd
from datetime import datetime
import json
import os
import streamlit as st

# === CONFIGURATION GLOBALE ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAT, LON = 43.66528, 1.3775
TIMEZONE = "Europe/Paris"
RAPPORT_FILE = os.path.join(BASE_DIR, "rapport_arrosage_openmeteo.txt")

CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json")
]

# === RÉCUPÉRATION MÉTÉO ===
@st.cache_data
def calculer_evapo(temp, rayonnement, vent):
    return 0.0023 * (temp + 17.8) * (rayonnement ** 0.5) * (vent + 1)

def recuperer_donnees_meteo():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max,precipitation_sum,windspeed_10m_max,shortwave_radiation_sum",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": TIMEZONE
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    df = pd.DataFrame({
        "date": pd.to_datetime(data["daily"]["time"]),
        "temp_max": data["daily"]["temperature_2m_max"],
        "pluie": data["daily"]["precipitation_sum"],
        "vent_max": data["daily"]["windspeed_10m_max"],
        "rayonnement": data["daily"]["shortwave_radiation_sum"],
    })

    df["evapo"] = calculer_evapo(df["temp_max"], df["rayonnement"], df["vent_max"])
    return df

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return pd.DataFrame({
        "date": pd.to_datetime(data["daily"]["time"]),
        "temp_max": data["daily"]["temperature_2m_max"],
        "pluie": data["daily"]["precipitation_sum"],
        "vent_max": data["daily"]["windspeed_10m_max"],
        "rayonnement": data["daily"]["shortwave_radiation_sum"]
    })


# === CHARGER LES PLANTES ===
def charger_plantes():
    for path in CANDIDATE_PATHS:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                plantes = json.load(f)
            return plantes
    return {
        "tomate": {"seuil_jours": 2},
        "courgette": {"seuil_jours": 2}
    }

# === GÉNÉRER LE RAPPORT ===
def generer_rapport(df, plantes):
    today = pd.to_datetime(datetime.now().date())
    df_passe = df[df["date"] < today]

    pluie_total = df_passe["pluie"].sum()
    jours_chauds = (df_passe["temp_max"] >= 28).sum()

    header = (
        f"📍 Météo à Beauzelle\n"
        f"-----------------------------------------\n"
        f"Période analysée : {df['date'].min().date()} → {df['date'].max().date()}\n"
        f"Pluie totale (7 jours passés) : {pluie_total:.1f} mm\n"
        f"Jours chauds (≥28°C) : {jours_chauds} jour(s)\n"
    )

    tableau = (
        "\n-----------------------------------------\n"
        "Date       | Température | Pluie (mm)\n"
        "-----------|-------------|------------"
    )
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%d/%m/%Y")
        tableau += f"\n{date_str}  |   {row['temp_max']:5.1f}°C    |   {row['pluie']:5.1f}"

    conclusion = "\n\n🌱 Recommandations par plante :\n"
    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", 3)
        besoin = (pluie_total < 5 and jours_chauds >= 2)
        nom = plante.capitalize()
        if besoin:
            conclusion += f"- {nom} : Il faut arroser si vous ne l'avez pas fait depuis plus de {seuil} jours.\n"
        else:
            conclusion += f"- {nom} : Pas besoin d’arroser si vous l’avez fait il y a moins de {seuil} jours.\n"

    rapport = header + tableau + conclusion
    with open(RAPPORT_FILE, "w", encoding="utf-8") as f:
        f.write(rapport)
    return rapport

# === INTERFACE STREAMLIT ===
st.set_page_config(page_title="🌱 Arrosage Potager", layout="centered")

st.title("🌿 Suivi Arrosage du Potager")
st.write("Analyse basée sur la météo des 7 derniers jours à **Beauzelle**.")

if st.button("🔄 Rafraîchir les données météo"):
    df = recuperer_donnees_meteo()
    plantes = charger_plantes()
    rapport = generer_rapport(df, plantes)
    st.success("✅ Rapport mis à jour !")

if os.path.exists(RAPPORT_FILE):
    with open(RAPPORT_FILE, "r", encoding="utf-8") as f:
        rapport = f.read()
    st.text_area("📋 Rapport actuel :", rapport, height=400)
    st.download_button("⬇️ Télécharger le rapport", rapport, file_name="rapport_arrosage.txt")
else:
    st.warning("Aucun rapport disponible. Cliquez sur 'Rafraîchir les données météo'.")
