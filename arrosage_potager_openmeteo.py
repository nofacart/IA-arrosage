import requests
from datetime import datetime
import json

# Coordonnées de Beauzelle
LAT, LON = 43.66528, 1.3775
type_plante = "potagère"

# Paramètres de l'API Open-Meteo (forecast standard)
url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": LAT,
    "longitude": LON,
    "timezone": "Europe/Paris",
    "past_days": 7,
    "forecast_days": 7,
    "daily": [
        "temperature_2m_max",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
        "shortwave_radiation_sum"
    ]
}

# Appel API
resp = requests.get(url, params=params)
data = resp.json()

# Affiche les clés pour vérifier
if "daily" not in data or not data["daily"]:
    print("❌ Erreur API : données météo manquantes.")
    print("🛠️ Données reçues :", list(data.keys()))
    print(json.dumps(data, indent=2))
    exit(1)

# Extraction des données journalières
daily = data["daily"]
dates = daily["time"]
temps_max = daily["temperature_2m_max"]
pluies = daily["precipitation_sum"]
et0 = daily["et0_fao_evapotranspiration"]
radiations = daily["shortwave_radiation_sum"]

# Passé (7 jours) et futur (7 jours)
passe = list(zip(dates[:7], temps_max[:7], pluies[:7], et0[:7], radiations[:7]))
futur = list(zip(dates[7:], temps_max[7:], pluies[7:], et0[7:], radiations[7:]))

# Analyse simplifiée
def analyse(liste):
    total_pluie = sum(p[2] for p in liste)
    total_et0 = sum(p[3] for p in liste)
    jours_secs = sum(1 for p in liste if p[2] < 1)
    jours_chauds = sum(1 for p in liste if p[1] > 30)
    return total_pluie, total_et0, jours_secs, jours_chauds

pluie_passe, et0_passe, secs_passe, chauds_passe = analyse(passe)
pluie_futur, et0_futur, secs_futur, chauds_futur = analyse(futur)
deficit_hydrique = et0_passe - pluie_passe

# Demande utilisateur
try:
    jours_depuis_arrosage = int(input("💬 Combien de jours depuis le dernier arrosage ? : "))
except ValueError:
    print("⚠️ Entrée invalide. On considère 10 jours par défaut.")
    jours_depuis_arrosage = 10

# Recommandation
if jours_depuis_arrosage <= 1:
    recommandation = "Pas d'arrosage (déjà arrosé récemment)"
elif jours_depuis_arrosage <= 3:
    if pluie_futur < 5 and secs_futur >= 3:
        recommandation = "Arrosage léger recommandé"
    else:
        recommandation = "Pas d'arrosage nécessaire"
else:
    if pluie_futur > 15:
        recommandation = "Pas d'arrosage (pluie prévue)"
    elif deficit_hydrique > 10 or chauds_futur >= 3:
        recommandation = "Arrosage conseillé (déficit hydrique important)"
    else:
        recommandation = "Arrosage modéré possible"

# Rapport météo jour par jour
ligne_tableau = "Date        | Tmax | Pluie | ET0 | Radiation\n"
ligne_tableau += "-" * 50 + "\n"
for d, t, p, e, r in passe + futur:
    ligne_tableau += f"{d} | {t:>4.1f} | {p:>5.1f} | {e:>4.1f} | {r:>9.1f}\n"

# Rapport final
rapport = f"""
📍 Rapport d'arrosage - Beauzelle
Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}

🌱 Type de plante : {type_plante}
💧 Dernier arrosage : il y a {jours_depuis_arrosage} jour(s)

-- Analyse Passée :
💧 Pluie cumulée : {pluie_passe:.1f} mm
🌤️ Evapotranspiration cumulée : {et0_passe:.1f} mm
🌡️ Jours chauds : {chauds_passe}
🌵 Jours secs : {secs_passe}

-- Prévision :
💧 Pluie à venir : {pluie_futur:.1f} mm
🌤️ ET0 prévue : {et0_futur:.1f} mm
🌡️ Jours >30°C : {chauds_futur}

🧠 Déficit hydrique estimé : {deficit_hydrique:.1f} mm
💧 Recommandation : {recommandation}

📊 Détail jour par jour :
{ligne_tableau}
"""

# Sauvegarde
with open("rapport_arrosage_openmeteo.txt", "w", encoding="utf-8") as f:
    f.write(rapport)

print("✅ Rapport généré avec succès : rapport_arrosage_openmeteo.txt")
