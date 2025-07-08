import requests
from datetime import datetime, timedelta
import os
import json
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 📍 Coordonnées de Beauzelle
latitude = 43.66528
longitude = 1.3775
altitude = 150
today = datetime.now().date()
days_back = 7
days_forward = 3

# 📁 Chargement des plantes
try:
    chemin_fichier = os.path.join(os.path.dirname(__file__), "plantes.json")
    with open(chemin_fichier, "r", encoding="utf-8") as f:
        plantes = json.load(f)
    print(f"✅ Plantes chargées depuis {chemin_fichier}")
except Exception as e:
    print(f"❌ Impossible de charger 'plantes.json' : {e}")
    plantes = {}

# 📆 Période analysée
start_past = today - timedelta(days=days_back)
end_future = today + timedelta(days=days_forward)

# 🌐 Requête Open-Meteo
url = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={latitude}&longitude={longitude}&altitude={altitude}"
    f"&daily=temperature_2m_max,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max"
    f"&timezone=Europe%2FParis"
    f"&start_date={start_past}&end_date={end_future}"
)

print("📡 Requête météo…")
response = requests.get(url)
if response.status_code != 200:
    print("❌ Erreur API :", response.text)
    exit()

data = response.json()
dates = data["daily"]["time"]
temp_max = data["daily"]["temperature_2m_max"]
precip = data["daily"]["precipitation_sum"]
radiation = data["daily"]["shortwave_radiation_sum"]
vent = data["daily"]["windspeed_10m_max"]
vent_ms = [v / 3.6 for v in vent]

# 🌿 Calcul simplifié ET₀ (FAO)
def calcul_evapotranspiration_fao(temp, rad, vent, altitude=150):
    albedo = 0.23
    G = 0
    R_s = rad
    u2 = vent
    R_n = (1 - albedo) * R_s
    delta = 4098 * (0.6108 * math.exp((17.27 * temp)/(temp + 237.3))) / ((temp + 237.3)**2)
    P = 101.3 * ((293 - 0.0065 * altitude) / 293)**5.26
    gamma = 0.665e-3 * P
    e_s = 0.6108 * math.exp((17.27 * temp)/(temp + 237.3))
    e_a = e_s * 0.5
    ET0 = (0.408 * delta * (R_n - G) + gamma * (900 / (temp + 273)) * u2 * (e_s - e_a)) / (
        delta + gamma * (1 + 0.34 * u2)
    )
    return round(max(ET0, 0), 2)

evapo = [
    calcul_evapotranspiration_fao(t, r, v)
    for t, r, v in zip(temp_max, radiation, vent_ms)
]

# 📊 Analyse
cumul_precip_passe = sum(p for d, p in zip(dates, precip) if datetime.strptime(d, "%Y-%m-%d").date() < today)
cumul_evapo_passe = sum(e for d, e in zip(dates, evapo) if datetime.strptime(d, "%Y-%m-%d").date() < today)
jours_chauds = sum(1 for d, t in zip(dates, temp_max) if datetime.strptime(d, "%Y-%m-%d").date() >= today and t >= 30)

if cumul_precip_passe >= 10:
    seuil = 5
elif jours_chauds >= 3 or cumul_evapo_passe >= 25:
    seuil = 2
else:
    seuil = 3

# 📄 Rapport
rapport = "-----------------------------------------\n"
rapport += "Date       | 🌡️Temp | 🌧️Pluie | 💨Vent | ☀️Rayon | ET₀ (mm)\n"
rapport += "-----------|--------|--------|--------|---------|---------\n"
for i in range(len(dates)):
    rapport += (
        f"{dates[i]} | {temp_max[i]:5.1f}°C | {precip[i]:5.1f}mm | "
        f"{vent[i]:5.1f}km/h | {radiation[i]:5.1f} | {evapo[i]:5.2f}\n"
    )

rapport += "-----------------------------------------\n"
rapport += "\n🌿 Conclusion :\n"
rapport += f"💧 Il faut arroser votre jardin si vous avez arrosé il y a plus de {seuil} jours.\n"

rapport += "\n🌱 Recommandations par plante :\n"
for nom, infos in plantes.items():
    besoin = infos.get("besoin", "moyen")
    if besoin == "fort":
        jours = seuil - 1
    elif besoin == "faible":
        jours = seuil + 1
    else:
        jours = seuil
    rapport += f"- {nom.capitalize()} : à arroser si cela fait plus de {jours} jours.\n"

# 🗂️ Répertoire du script en cours (même si lancé depuis ailleurs)
script_dir = os.path.dirname(os.path.abspath(__file__))

# 📄 Chemin complet vers le rapport
rapport_path = os.path.join(script_dir, "rapport_arrosage_openmeteo.txt")

# 💾 Sauvegarde du rapport dans le bon répertoire
with open(rapport_path, "w", encoding="utf-8") as f:
    f.write(rapport)

print(f"✅ Rapport généré : {rapport_path}")

# ✉️ Envoi d’email
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

if EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECEIVER:
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = "🌱 Rapport Arrosage – " + datetime.now().strftime("%d/%m/%Y")
        msg.attach(MIMEText(rapport, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print("❌ Erreur envoi email :", e)
else:
    print("⚠️ Paramètres email manquants, email non envoyé.")
