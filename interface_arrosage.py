import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import requests

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

# --- FONCTION : Récupérer météo depuis Open-Meteo ---
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

# --- FONCTION : Charger plantes.json avec fallback ---
def charger_plantes():
    for path in CANDIDATE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    plantes = json.load(f)
                print(f"✅ Chargé plantes depuis {path}")
                return plantes
            except Exception as e:
                print(f"❌ Erreur lecture {path} : {e}")
    # fallback : créer un template minimal
    exemple = {
        "tomate": {"seuil_jours": 2},
        "courgette": {"seuil_jours": 2},
        "haricot vert": {"seuil_jours": 3},
        "melon": {"seuil_jours": 3},
        "fraise": {"seuil_jours": 2},
        "aromatiques": {"seuil_jours": 5}
    }
    print("⚠️ Aucun plantes.json trouvé. Utilisation d'un exemple minimal :", exemple)
    return exemple

# --- FONCTION : Générer rapport et afficher interface ---
def generer_interface():
    st.title("💧 Arrosage potager - Recommandations personnalisées")

    try:
        df = recuperer_donnees_meteo()
        plantes = charger_plantes()
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données : {e}")
        return

    today = pd.to_datetime(datetime.now().date())
    df_passe = df[df["date"] < today]

    # Calculs météo
    pluie_total_passe = df_passe["pluie"].sum()
    jours_chauds = (df_passe["temp_max"] >= 28).sum()

    # Affichage des données météo clés
    st.subheader("📊 Données météo (7 derniers jours)")
    st.write(f"- Pluie totale passée : **{pluie_total_passe:.1f} mm**")
    st.write(f"- Nombre de jours chauds (≥28°C) : **{jours_chauds}**")

    # Mode logique d'évaluation globale
    mode_logique = st.radio("Mode logique pour besoin global d'arrosage :", options=["AND", "OR"], index=0)

    if mode_logique == "AND":
        besoin_arrosage_global = (pluie_total_passe < 5 and jours_chauds >= 2)
    else:
        besoin_arrosage_global = (pluie_total_passe < 5 or jours_chauds >= 2)

    st.write(f"**Besoin global d'arrosage :** {'Oui' if besoin_arrosage_global else 'Non'}")

    # Slider pour jours depuis dernier arrosage
    jours_depuis_arrosage = st.slider("Depuis combien de jours avez-vous arrosé ?", min_value=0, max_value=10, value=3)

    # Recommandations par plante
    st.subheader("🌱 Recommandations personnalisées par plante :")
    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", 3)
        nom = plante.capitalize()
        if besoin_arrosage_global and jours_depuis_arrosage > seuil:
            st.success(f"- {nom} : Il faut arroser (arrosé il y a {jours_depuis_arrosage} jours, seuil {seuil})")
        else:
            st.info(f"- {nom} : Pas besoin d'arroser (arrosé il y a {jours_depuis_arrosage} jours, seuil {seuil})")

    # Optionnel : affichage du tableau météo complet
    st.subheader("Données météo détaillées (passé + prévisions)")
    st.dataframe(df.style.format({"temp_max": "{:.1f} °C", "pluie": "{:.1f} mm"}))


if __name__ == "__main__":
    generer_interface()
