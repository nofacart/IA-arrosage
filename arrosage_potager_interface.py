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
        "courgette": {"seuil_jours": 2}
    }
    print("⚠️ Aucun plantes.json trouvé. Utilisation d'un exemple minimal :", exemple)
    return exemple

# --- FONCTION : Générer le rapport ---
def generer_rapport(df, plantes):
    today = pd.to_datetime(datetime.now().date())
    df_passe = df[df["date"] < today]

    pluie_total = df_passe["pluie"].sum()
    jours_chauds = (df_passe["temp_max"] >= 28).sum()

    # Header
    header = (
        f"📍 Météo à Beauzelle\n"
        f"-----------------------------------------\n"
        f"Période analysée : {df['date'].min().date()} → {df['date'].max().date()}\n"
        f"Pluie totale (7 jours passés) : {pluie_total:.1f} mm\n"
        f"Jours chauds (≥28°C) : {jours_chauds} jour(s)\n"
    )

    # Tableau
    tableau = (
        "\n-----------------------------------------\n"
        "Date       | Température | Pluie (mm)\n"
        "-----------|-------------|------------"
    )
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%d/%m/%Y")
        tableau += f"\n{date_str}  |   {row['temp_max']:5.1f}°C    |   {row['pluie']:5.1f}"

    # Recommandations par plante
    conclusion = "\n\n🌱 Recommandations par plante :\n"
    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", 3)
        besoin = (pluie_total < 5 and jours_chauds >= 2)
        nom = plante.capitalize()
        if besoin:
            conclusion += f"- {nom} : Il faut arroser si vous ne l'avez pas fait depuis plus de {seuil} jours.\n"
        else:
            conclusion += f"- {nom} : Pas besoin d’arroser si vous l’avez fait il y a moins de {seuil} jours.\n"

    # Assemblage et écriture
    rapport = header + tableau + conclusion
    with open(RAPPORT_FILE, "w", encoding="utf-8") as f:
        f.write(rapport)
    print(f"✅ Rapport généré : {RAPPORT_FILE}")

# --- LANCEMENT ---
if __name__ == "__main__":
    try:
        df_meteo = recuperer_donnees_meteo()
        plantes = charger_plantes()
        generer_rapport(df_meteo, plantes)
    except Exception as err:
        print(f"❌ Erreur : {err}")
