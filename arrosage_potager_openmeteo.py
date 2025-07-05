import requests
from datetime import datetime, timedelta

# Configuration
latitude = 43.66528
longitude = 1.3775
days_back = 7
days_forward = 3

# Obtenir les dates
today = datetime.now().date()
start_past = today - timedelta(days=days_back)
end_future = today + timedelta(days=days_forward)

# Format ISO pour l’API
start_past_str = start_past.isoformat()
end_future_str = end_future.isoformat()

# 📦 API Open-Meteo (historique + prévisions)
url = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={latitude}&longitude={longitude}"
    f"&daily=temperature_2m_max,precipitation_sum"
    f"&timezone=Europe%2FParis"
    f"&start_date={start_past_str}&end_date={end_future_str}"
)

print("📡 Requête météo en cours...")
response = requests.get(url)

if response.status_code != 200:
    print("❌ Erreur API :", response.text)
    exit()

data = response.json()

dates = data["daily"]["time"]
temp_max = data["daily"]["temperature_2m_max"]
precip = data["daily"]["precipitation_sum"]

# Analyse
cumul_precip_passe = sum(
    p for d, p in zip(dates, precip) if datetime.strptime(d, "%Y-%m-%d").date() < today
)
cumul_precip_futur = sum(
    p for d, p in zip(dates, precip) if datetime.strptime(d, "%Y-%m-%d").date() >= today
)
jours_chauds = sum(
    1 for d, t in zip(dates, temp_max)
    if datetime.strptime(d, "%Y-%m-%d").date() >= today and t >= 30
)

# Déterminer un seuil d’arrosage
if cumul_precip_passe + cumul_precip_futur >= 10:
    seuil_arrosage = 5
elif jours_chauds >= 3:
    seuil_arrosage = 2
else:
    seuil_arrosage = 3

# ✍️ Génération du rapport
rapport = "-----------------------------------------\n"
rapport += "Date       | Température | Pluie (mm)\n"
rapport += "-----------|-------------|------------\n"

for d, t, p in zip(dates, temp_max, precip):
    rapport += f"{d}  |   {t:5.1f}°C    |   {p:.1f}\n"

rapport += "-----------------------------------------\n"
rapport += f"\n🌿 Conclusion :\n"
rapport += f"💧 Il faut arroser votre jardin si vous avez arrosé il y a plus de {seuil_arrosage} jours.\n"

# 💾 Sauvegarde dans le fichier
with open("rapport_arrosage_openmeteo.txt", "w", encoding="utf-8") as f:
    f.write(rapport)

print("✅ Rapport généré avec succès : rapport_arrosage_openmeteo.txt")
