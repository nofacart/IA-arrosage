import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import json
import os

# === BASE_DIR : dossier où se trouve ce script ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CONFIGURATION ---
LAT, LON = 43.66528, 1.3775          # Beauzelle
TIMEZONE = "Europe/Paris"
RAPPORT_FILE = os.path.join(BASE_DIR, "rapport_arrosage_openmeteo.txt")

# Emplacements possibles de plantes.json
CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json")
]

def recuperer_donnees_meteo():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max,precipitation_sum",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": TIMEZONE
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return pd.DataFrame({
        "date": pd.to_datetime(data["daily"]["time"]),
        "temp_max": data["daily"]["temperature_2m_max"],
        "pluie": data["daily"]["precipitation_sum"]
    })

def charger_plantes():
    for path in CANDIDATE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    plantes = json.load(f)
                st.success(f"✅ Plantes chargées depuis {path}")
                return plantes
            except Exception as e:
                st.error(f"❌ Erreur lecture {path} : {e}")
    exemple = {
        "tomate": {"seuil_jours": 3},
        "courgette": {"seuil_jours": 3},
        "haricot vert": {"seuil_jours": 3},
        "melon": {"seuil_jours": 3},
        "fraise": {"seuil_jours": 3},
        "aromatiques": {"seuil_jours": 3},
    }
    st.warning("⚠️ Aucun plantes.json trouvé. Utilisation d'un exemple minimal.")
    return exemple

def generer_rapport(df, plantes, jours_depuis_arrosage):
    today = pd.to_datetime(datetime.now().date())
    df_passe = df[df["date"] < today]
    df_futur = df[df["date"] >= today]

    pluie_total_passe = df_passe["pluie"].sum()
    pluie_total_futur = df_futur["pluie"].sum()
    jours_chauds = (df_passe["temp_max"] >= 28).sum()

    if pluie_total_passe + pluie_total_futur >= 10:
        seuil_arrosage_global = 5
    elif jours_chauds >= 3:
        seuil_arrosage_global = 2
    else:
        seuil_arrosage_global = 3

    besoin_arrosage_global = (pluie_total_passe < 5 and jours_chauds >= 2)

    header = (
        f"📍 Météo à Beauzelle\n"
        f"-----------------------------------------\n"
        f"Période analysée : {df['date'].min().date()} → {df['date'].max().date()}\n"
        f"Pluie totale passée (7j) : {pluie_total_passe:.1f} mm\n"
        f"Pluie totale à venir (7j) : {pluie_total_futur:.1f} mm\n"
        f"Jours chauds (≥28°C sur passé) : {jours_chauds}\n"
        f"Seuil arrosage global ajusté : {seuil_arrosage_global} jours\n"
    )

    tableau = (
        "\n-----------------------------------------\n"
        "Date       | Température | Pluie (mm)\n"
        "-----------|-------------|------------"
    )
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%d/%m/%Y")
        tableau += f"\n{date_str}  |   {row['temp_max']:5.1f}°C    |   {row['pluie']:5.1f}"

    conclusion = "\n\n🌱 Recommandations personnalisées par plante :\n"
    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", seuil_arrosage_global)
        nom = plante.capitalize()
        if besoin_arrosage_global and jours_depuis_arrosage > seuil:
            conclusion += f"- {nom} : Il faut arroser, vous avez arrosé il y a {jours_depuis_arrosage} jours (> seuil {seuil}).\n"
        else:
            conclusion += f"- {nom} : Pas besoin d'arroser (arrosé il y a {jours_depuis_arrosage} jours, seuil {seuil}).\n"

    rapport = header + tableau + conclusion

    with open(RAPPORT_FILE, "w", encoding="utf-8") as f:
        f.write(rapport)

    return rapport

# --- STREAMLIT APP ---
st.title("🌱 Arrosage Potager - Recommandations personnalisées")

try:
    df_meteo = recuperer_donnees_meteo()
    plantes = charger_plantes()

    st.markdown("### 🌤️ Données météo (7 derniers jours + 7 prochains jours)")
    st.dataframe(df_meteo.style.format({"temp_max": "{:.1f} °C", "pluie": "{:.1f} mm"}))

    # Slider ici pour sélectionner les jours depuis dernier arrosage
    jours_depuis_arrosage = st.slider(
        "Il y a combien de jours que vous avez arrosé votre jardin ?",
        min_value=0, max_value=30, value=3, step=1
    )

    rapport = generer_rapport(df_meteo, plantes, jours_depuis_arrosage)

    st.markdown("### 📄 Rapport généré")
    st.text(rapport)

    st.success(f"✅ Rapport sauvegardé dans : {RAPPORT_FILE}")

except Exception as err:
    st.error(f"❌ Une erreur est survenue : {err}")
