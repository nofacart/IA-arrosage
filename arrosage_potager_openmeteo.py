import requests
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json

# === CONFIGURATION ===

latitude = 43.66528
longitude = 1.3775
days_back = 7
days_forward = 3
timezone = "Europe/Paris"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANTES_FILE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json"),
]

RAPPORT_FILE = os.path.join(BASE_DIR, "rapport_arrosage_openmeteo.txt")

# Email (via secrets GitHub Actions)
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# === FONCTIONS ===

def charger_plantes():
    for path in PLANTES_FILE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    plantes = json.load(f)
                print(f"✅ Chargé plantes depuis {path}")
                return plantes
            except Exception as e:
                print(f"❌ Erreur lecture {path} : {e}")
    # fallback minimal
    exemple = {
        "tomate": {"seuil_jours": 3},
        "courgette": {"seuil_jours": 3},
        "haricot vert": {"seuil_jours": 3},
        "melon": {"seuil_jours": 3},
        "fraise": {"seuil_jours": 3},
        "aromatiques": {"seuil_jours": 3},
    }
    print("⚠️ Aucun plantes.json trouvé, usage d’un exemple minimal :", exemple)
    return exemple

def recuperer_donnees_meteo():
    today = datetime.now().date()
    start_past = today - timedelta(days=days_back)
    end_future = today + timedelta(days=days_forward)

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,precipitation_sum"
        f"&timezone={timezone.replace('/', '%2F')}"
        f"&start_date={start_past.isoformat()}&end_date={end_future.isoformat()}"
    )

    print("📡 Requête météo en cours...")
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    return data

def analyser_donnees(data):
    dates = data["daily"]["time"]
    temp_max = data["daily"]["temperature_2m_max"]
    precip = data["daily"]["precipitation_sum"]
    today = datetime.now().date()

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
    return dates, temp_max, precip, cumul_precip_passe, cumul_precip_futur, jours_chauds

def calcul_seuil_arrosage(cumul_precip_passe, cumul_precip_futur, jours_chauds):
    if cumul_precip_passe + cumul_precip_futur >= 10:
        return 5
    elif jours_chauds >= 3:
        return 2
    else:
        return 3

def generer_rapport(dates, temp_max, precip, seuil_arrosage, plantes, cumul_precip_passe, jours_chauds):
    rapport = (
        f"📍 Météo à Beauzelle\n"
        f"Analyse du {dates[0]} au {dates[-1]}\n"
        f"Pluie totale passée (7j) : {cumul_precip_passe:.1f} mm\n"
        f"Jours chauds à venir (≥30°C) : {jours_chauds}\n"
        f"-----------------------------------------\n"
        "Date       | Température | Pluie (mm)\n"
        "-----------|-------------|------------\n"
    )
    for d, t, p in zip(dates, temp_max, precip):
        rapport += f"{d}  |   {t:5.1f}°C    |   {p:.1f}\n"
    rapport += "-----------------------------------------\n\n"
    rapport += "🌱 Recommandations par plante :\n"

    besoin_arroser = (cumul_precip_passe < 5 and jours_chauds >= 2)

    for plante, infos in plantes.items():
        seuil = infos.get("seuil_jours", 3)
        nom = plante.capitalize()
        if besoin_arroser:
            rapport += f"- {nom} : Il faut arroser si vous ne l'avez pas fait depuis plus de {seuil} jours.\n"
        else:
            rapport += f"- {nom} : Pas besoin d’arroser si vous l’avez fait il y a moins de {seuil} jours.\n"

    rapport += (
        f"\n🌿 Conclusion :\n"
        f"💧 Il faut arroser votre jardin si vous avez arrosé il y a plus de {seuil_arrosage} jours.\n"
    )

    with open(RAPPORT_FILE, "w", encoding="utf-8") as f:
        f.write(rapport)

    print(f"✅ Rapport généré : {RAPPORT_FILE}")
    return rapport

def envoyer_email(contenu):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = "🌱 Rapport Arrosage – " + datetime.now().strftime("%d/%m/%Y")
        msg.attach(MIMEText(contenu, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print("❌ Erreur envoi email :", e)

# === MAIN ===
if __name__ == "__main__":
    try:
        plantes = charger_plantes()
        data = recuperer_donnees_meteo()
        dates, temp_max, precip, cumul_precip_passe, cumul_precip_futur, jours_chauds = analyser_donnees(data)
        seuil_arrosage = calcul_seuil_arrosage(cumul_precip_passe, cumul_precip_futur, jours_chauds)
        rapport = generer_rapport(dates, temp_max, precip, seuil_arrosage, plantes, cumul_precip_passe, jours_chauds)
        envoyer_email(rapport)
    except Exception as e:
        print(f"❌ Erreur : {e}")
