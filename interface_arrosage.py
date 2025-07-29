import streamlit as st
import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import json
import os
import math
from datetime import datetime
import locale
from babel.dates import format_date
from PIL import Image
import io

# 🌍 Localisation en français pour les dates
#locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")



# === Chemins de base ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAM_PATH = os.path.join(BASE_DIR, "parametres_utilisateur.json")
JOURNAL_PATH = os.path.join(BASE_DIR, "journal_jardin.json")
ETAT_JARDIN_FILE = os.path.join(BASE_DIR, "etat_jardin.json")
METEO_HISTORIQUE_DISPONIBLE = 7

# === Chargement / Sauvegarde des préférences utilisateur ===
def charger_preferences_utilisateur():
    """Charge les préférences utilisateur depuis un fichier JSON local.

    Retourne un dictionnaire des préférences utilisateur si le fichier existe et est valide,
    sinon un dictionnaire vide.

    Returns:
        dict: Préférences utilisateur.
    """
    if os.path.exists(PARAM_PATH):
        try:
            with open(PARAM_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
    return {}

def enregistrer_preferences_utilisateur(prefs: dict):
    """Enregistre les préférences utilisateur dans un fichier JSON.

    Args:
        prefs (dict): Dictionnaire des préférences utilisateur à sauvegarder.
    """
    try:
        with open(PARAM_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde des préférences : {e}")

# === Chargement des familles de plantes ===
def charger_familles():
    """Charge les données des familles de plantes depuis un fichier JSON.

    Returns:
        dict: Dictionnaire des familles de plantes.
    """
    path = os.path.join(BASE_DIR, "familles_plantes.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Construction d'un index plante → kc + famille
def construire_index_plantes(familles):
    """Construit un index des plantes associant chaque plante à sa famille et son coefficient kc.

    Args:
        familles (dict): Dictionnaire des familles de plantes.

    Returns:
        dict: Index plantes avec famille et kc.
    """
    index = {}
    for famille, infos in familles.items():
        for plante in infos["plantes"]:
            index[plante] = {
                "famille": famille,
                "kc": infos["kc"]
            }
    return index

@st.cache_data
def charger_recommandations_mensuelles(filepath="recommandations_jardin.json"):
    """
    Charge les recommandations mensuelles depuis un fichier JSON.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Convertir les clés de mois en int si elles sont des chaînes
            return {int(k): v for k, v in data.items()}
    except FileNotFoundError:
        st.error(f"Fichier de recommandations '{filepath}' introuvable.")
        return {}
    except json.JSONDecodeError:
        st.error(f"Erreur de lecture du fichier JSON '{filepath}'. Vérifiez le format.")
        return {}
    
# === Météo : géocodage d'une ville vers latitude/longitude ===
@st.cache_data(ttl=86400)
def get_coords_from_city(city_name):
    """Récupère les coordonnées géographiques (latitude, longitude) d'une ville donnée.

    Args:
        city_name (str): Nom de la ville.

    Returns:
        dict or None: Dictionnaire avec les clés 'lat', 'lon', 'name', 'country' ou None si non trouvé.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city_name, "count": 1, "language": "fr", "format": "json"}
    r = requests.get(url, params=params)
    r.raise_for_status()
    results = r.json().get("results")
    if results:
        first = results[0]
        return {
            "lat": first["latitude"],
            "lon": first["longitude"],
            "name": first["name"],
            "country": first.get("country", "")
        }
    return None

# === Calcul FAO ET₀ simplifié ===
def calcul_evapotranspiration_fao(temp, rad, vent, altitude=150):
    """Calcule l'évapotranspiration de référence (ET₀) selon la méthode FAO simplifiée.

    Args:
        temp (float): Température maximale quotidienne en °C.
        rad (float): Radiation solaire (W/m²).
        vent (float): Vitesse du vent en m/s.
        altitude (int, optional): Altitude en mètres. Défaut à 150.

    Returns:
        float: ET₀ arrondi à deux décimales.
    """
    albedo = 0.23
    G = 0  # Flux de chaleur au sol
    R_n = (1 - albedo) * rad
    delta = 4098 * (0.6108 * math.exp((17.27 * temp)/(temp + 237.3))) / ((temp + 237.3)**2)
    P = 101.3 * ((293 - 0.0065 * altitude) / 293)**5.26
    gamma = 0.665e-3 * P
    e_s = 0.6108 * math.exp((17.27 * temp)/(temp + 237.3))
    e_a = e_s * 0.5  # HR = 50% approx
    u2 = vent
    ET0 = (0.408 * delta * (R_n - G) + gamma * (900 / (temp + 273)) * u2 * (e_s - e_a)) / (
        delta + gamma * (1 + 0.34 * u2)
    )
    return round(max(ET0, 0), 2)

# === Données météo quotidiennes ===
@st.cache_data(ttl=86400)
def recuperer_meteo(lat, lon):
    """Récupère les données météo journalières pour une latitude et longitude données.

    Args:
        lat (float): Latitude.
        lon (float): Longitude.

    Returns:
        pandas.DataFrame: Données météo quotidiennes avec colonnes 'date', 'temp_max', 'pluie', 'radiation', 'vent', 'evapo'.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max,et0_fao_evapotranspiration",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": "Europe/Paris"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    d = r.json()["daily"]

    temp = d["temperature_2m_max"]
    pluie = d["precipitation_sum"]
    rad = d.get("shortwave_radiation_sum", [None] * len(temp))
    vent_kmh = d.get("windspeed_10m_max", [None] * len(temp))
    evapo = d.get("et0_fao_evapotranspiration")

    # Calcul si ET₀ manquant
    if evapo is None or any(e is None for e in evapo):
        evapo_calc = []
        for t, r_, v in zip(temp, rad, vent_kmh):
            if None in (t, r_, v):
                evapo_calc.append(0)
            else:
                evapo_calc.append(calcul_evapotranspiration_fao(t, r_, v / 3.6))  # km/h → m/s
        evapo = evapo_calc

    return pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "temp_max": temp,
        "pluie": pluie,
        "radiation": rad,
        "vent": vent_kmh,
        "evapo": evapo
    })

# === Estimation de l’arrosage le plus contraignant ===
def estimer_arrosage_le_plus_contraignant(df_futur, plantes_choisies, index_plantes, seuil_deficit, facteur_sol, facteur_paillage):
    """Estime la date du prochain arrosage le plus urgent parmi les plantes sélectionnées.

    Args:
        df_futur (pandas.DataFrame): Données météo futures.
        plantes_choisies (list): Liste des plantes sélectionnées.
        index_plantes (dict): Index des plantes avec coefficients kc.
        seuil_deficit (float): Seuil de déficit hydrique en mm.
        facteur_sol (float): Facteur multiplicatif selon type de sol.
        facteur_paillage (float): Facteur multiplicatif selon présence de paillage.

    Returns:
        datetime.date or None: Date estimée du prochain arrosage ou None si pas nécessaire.
    """
    dates_arrosage = []

    for plante in plantes_choisies:
        kc = index_plantes.get(plante, {}).get("kc", 1.0)
        cumul_deficit = 0

        for _, row in df_futur.iterrows():
            etc = row["evapo"] * kc * facteur_sol * facteur_paillage
            bilan = row["pluie"] - etc
            if bilan < 0:
                cumul_deficit += -bilan
            if cumul_deficit >= seuil_deficit:
                dates_arrosage.append(row["date"])
                break  # seuil atteint

    return min(dates_arrosage) if dates_arrosage else None

# === Croissance de l’herbe (mm/jour) ===
def croissance_herbe(temp_moy, pluie, et0):
    """Estime la croissance quotidienne de l'herbe en fonction des conditions météo.

    Args:
        temp_moy (float): Température moyenne (°C).
        pluie (float): Précipitations journalières (mm).
        et0 (float): Évapotranspiration de référence (mm).

    Returns:
        float: Croissance estimée en mm/jour.
    """
    bilan_hydrique = pluie - et0

    if temp_moy < 10:
        croissance = 0.5
    elif 10 <= temp_moy < 15:
        croissance = 1.5
    elif 15 <= temp_moy < 25:
        croissance = 4
    elif temp_moy >= 25:
        croissance = 2
    else:
        croissance = 1

    if bilan_hydrique < -5:
        croissance *= 0.3
    elif bilan_hydrique < 0:
        croissance *= 0.6
    elif bilan_hydrique > 5:
        croissance *= 1.2

    return round(max(croissance, 0), 2)

# === Estimation de la prochaine tonte ===
def estimer_date_prochaine_tonte(df_futur, hauteur_actuelle, taille_cible):
    """Estime la date de la prochaine tonte basée sur la croissance du gazon.

    Args:
        df_futur (pandas.DataFrame): Données météo futures.
        hauteur_actuelle (float): Hauteur actuelle du gazon en cm.
        taille_cible (float): Hauteur cible de pelouse en cm.

    Returns:
        datetime.date or None: Date estimée de la prochaine tonte ou None si non estimée.
    """
    hauteur_limite = 1.5 * taille_cible
    hauteur = hauteur_actuelle

    for _, row in df_futur.iterrows():
        temp_moy = row["temp_max"]
        pluie = row["pluie"]
        evapo = row["evapo"]  # ou ET0, selon nom colonne

        bilan_hydrique = pluie - evapo
        if temp_moy < 10:
            croissance = 0.5
        elif 10 <= temp_moy < 15:
            croissance = 1.5
        elif 15 <= temp_moy < 25:
            croissance = 4
        elif temp_moy >= 25:
            croissance = 2
        else:
            croissance = 1

        if bilan_hydrique < -5:
            croissance *= 0.3
        elif bilan_hydrique < 0:
            croissance *= 0.6
        elif bilan_hydrique > 5:
            croissance *= 1.2

        croissance = round(max(croissance, 0), 2)
        hauteur += croissance/10

        if hauteur >= hauteur_limite:
            return row["date"]

    return None

def afficher_evolution_pelouse(journal, df, today):
    """Affiche un graphique de l'évolution estimée de la hauteur de la pelouse.

    Args:
        journal (dict): Journal des tontes et arrosages.
        df (pandas.DataFrame): Données météo.
        today (datetime.date): Date actuelle.
    """
    if not journal["tontes"]:
        st.info("Aucune tonte enregistrée.")
        return

    # Cas où les dates sont des chaînes ou des listes
    def parser_date_tonte(t):
        if isinstance(t["date"], list):
            return max(pd.to_datetime(d) for d in t["date"])
        return pd.to_datetime(t["date"])

    dates_tontes = [parser_date_tonte(t) for t in journal["tontes"]]
    hauteurs_tontes = [t["hauteur"] for t in journal["tontes"]]

    hauteur = hauteurs_tontes[0]
    historique = []

    last_tonte_index = 0
    df_futur = df[df["date"] >= dates_tontes[0]]
    for date in df_futur["date"]:
        if last_tonte_index + 1 < len(dates_tontes) and date >= dates_tontes[last_tonte_index + 1]:
            last_tonte_index += 1
            hauteur = hauteurs_tontes[last_tonte_index]

        row = df[df["date"] == date]
        if not row.empty:
            croissance = croissance_herbe(row["temp_max"].values[0], row["pluie"].values[0], row["evapo"]) / 10
            hauteur += croissance

        historique.append({"date": date, "hauteur": hauteur})

    df_hauteur = pd.DataFrame(historique)

    # --- Affichage graphique ---
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df_hauteur["date"], df_hauteur["hauteur"], label="Hauteur estimée", color="green")
    ax.scatter(dates_tontes, hauteurs_tontes, color="red", label="Tonte", zorder=5)
    ax.axhline(y=hauteurs_tontes[-1] * 1.5, color='orange', linestyle='--', label='Seuil max conseillé')

    ax.set_ylabel("Hauteur (cm)")
    ax.set_xlabel("Date")
    ax.set_title("Évolution estimée de la hauteur de pelouse")
    ax.legend()
    ax.grid(True)

    # Axe X plus lisible
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    plt.xticks(rotation=45)

    st.pyplot(fig)

def afficher_calendrier_frise(journal, today):
    """Affiche une frise de 14 jours avec les actions de jardin (arrosage, tonte).

    Args:
        journal (dict): Journal des actions réalisées.
        today (datetime.date): Date actuelle.
    """
    jours = [today - pd.Timedelta(days=i) for i in range(13, -1, -1)]
    dates_arrosage = set(pd.to_datetime(d).date() for d in journal.get("arrosages", []))
    dates_tonte = set(pd.to_datetime(t["date"]).date() for t in journal.get("tontes", []))

    lignes = []
    for jour in jours:
        jour_nom = jour.strftime("%a %d").capitalize()
        jour_date = jour.date()

        if jour_date in dates_arrosage:
            emoji = "✅"
            action = "Arrosé"
            couleur = "#D4EDDA"  # Vert clair
        elif jour_date in dates_tonte:
            emoji = "✂️"
            action = "Tondu"
            couleur = "#D6EAF8"  # Bleu clair
        else:
            emoji = "—"
            action = "Aucune action"
            couleur = "#F0F0F0"  # Gris clair

        lignes.append(f"""
            <div style="
                background-color: {couleur};
                display: inline-block;
                padding: 6px 10px;
                margin: 4px;
                border-radius: 6px;
                font-family: Segoe UI, sans-serif;
                font-size: 0.85em;
                text-align: center;
                min-width: 90px;
            ">
                📅 <b>{jour_nom}</b><br>{emoji} {action}
            </div>
        """)

    st.markdown("### 📅 Mon Jardin (14 jours en frise)")
    st.markdown("".join(lignes), unsafe_allow_html=True)

@st.cache_data
def calculer_stats_arrosage(journal):
    """
    Calcule les statistiques d'arrosage.
    Args:
        journal (dict): Dictionnaire contenant la liste des arrosages (pd.Timestamp).
    Returns:
        dict: Statistiques calculées.
    """
    arrosages = journal.get("arrosages", [])
    if len(arrosages) < 2:
        return {
            "nb_arrosages": len(arrosages),
            "freq_moyenne_jours": "N/A",
            "dernier_arrosage_date": arrosages[-1].date() if arrosages else None
        }

    # S'assurer que les dates sont triées
    arrosages_sorted = sorted(arrosages)
    
    # Calculer les écarts en jours entre arrosages consécutifs
    ecarts = []
    for i in range(1, len(arrosages_sorted)):
        delta = arrosages_sorted[i] - arrosages_sorted[i-1]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0

    return {
        "nb_arrosages": len(arrosages),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "dernier_arrosage_date": arrosages_sorted[-1].date()
    }

@st.cache_data
def calculer_stats_tonte(journal):
    """
    Calcule les statistiques de tonte.
    Args:
        journal (dict): Dictionnaire contenant la liste des tontes.
    Returns:
        dict: Statistiques calculées.
    """
    tontes = journal.get("tontes", [])
    if len(tontes) < 2:
        return {
            "nb_tontes": len(tontes),
            "freq_moyenne_jours": "N/A",
            "hauteur_moyenne": tontes[-1]["hauteur"] if tontes else "N/A",
            "derniere_tonte_date": tontes[-1]["date"].date() if tontes else None
        }

    # S'assurer que les tontes sont triées par date
    tontes_sorted = sorted(tontes, key=lambda x: x["date"])
    
    # Calculer les écarts en jours entre tontes consécutives
    ecarts = []
    for i in range(1, len(tontes_sorted)):
        delta = tontes_sorted[i]["date"] - tontes_sorted[i-1]["date"]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0
    hauteurs = [t["hauteur"] for t in tontes]
    hauteur_moyenne = sum(hauteurs) / len(hauteurs)

    return {
        "nb_tontes": len(tontes),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "hauteur_moyenne": round(hauteur_moyenne, 1),
        "derniere_tonte_date": tontes_sorted[-1]["date"].date()
    }

# === Journal des actions (arrosage et tonte) ===
def charger_journal():
    if os.path.exists(JOURNAL_PATH):
        try:
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            # --- Process 'arrosages' list ---
            if "arrosages" in data and isinstance(data["arrosages"], list):
                processed_arrosages = []
                for d_str in data["arrosages"]:
                    try:
                        processed_arrosages.append(pd.to_datetime(d_str))
                    except (ValueError, TypeError):
                        # Handle cases where a date string might be malformed
                        st.warning(f"Impossible de convertir la date d'arrosage '{d_str}'. Ignorée.")
                        continue
                data["arrosages"] = processed_arrosages
            else:
                data["arrosages"] = [] # Ensure it's a list if missing or wrong type

            # --- Process 'tontes' list ---
            if "tontes" in data and isinstance(data["tontes"], list):
                processed_tontes = []
                for tonte_entry in data["tontes"]:
                    if isinstance(tonte_entry, dict) and "date" in tonte_entry:
                        date_val = tonte_entry["date"]
                        try:
                            # Handle the specific case where 'date' might be a list (backward compatibility)
                            if isinstance(date_val, list):
                                # Convert list of date strings to Timestamps, find max, then convert to single Timestamp
                                tonte_dates_parsed = [pd.to_datetime(d) for d in date_val]
                                tonte_entry["date"] = max(tonte_dates_parsed)
                            elif isinstance(date_val, str):
                                # Ensure single date string is converted to Timestamp
                                tonte_entry["date"] = pd.to_datetime(date_val)
                            # If it's already a Timestamp, leave it as is
                            elif not isinstance(date_val, pd.Timestamp):
                                raise ValueError("Date de tonte inattendue.") # Catch non-str/non-list types

                            processed_tontes.append(tonte_entry)

                        except (ValueError, TypeError) as e:
                            st.warning(f"Impossible de convertir la date de tonte '{date_val}'. Entrée ignorée. Erreur: {e}")
                            continue # Skip this malformed entry
                    else:
                        st.warning(f"Entrée de tonte mal formée : {tonte_entry}. Ignorée.")
                data["tontes"] = processed_tontes
            else:
                data["tontes"] = [] # Ensure it's a list if missing or wrong type

            return data
        except json.JSONDecodeError as e:
            st.error(f"Erreur de lecture du fichier journal_jardin.json. Le fichier est peut-être corrompu ou mal formaté. Erreur: {e}")
            # Consider backing up or deleting the corrupt file if this happens often
            return {"arrosages": [], "tontes": []}
        except Exception as e:
            st.error(f"Une erreur inattendue est survenue lors du chargement du journal : {e}")
            return {"arrosages": [], "tontes": []}
    return {"arrosages": [], "tontes": []}

def sauvegarder_journal(data):
    data_to_save = data.copy()

    if "arrosages" in data_to_save and data_to_save["arrosages"]:
        data_to_save["arrosages"] = [d.isoformat() for d in data_to_save["arrosages"]]

    if "tontes" in data_to_save and data_to_save["tontes"]:
        for tonte in data_to_save["tontes"]:
            if isinstance(tonte.get("date"), pd.Timestamp):
                tonte["date"] = tonte["date"].isoformat()

    try:
        with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde du journal : {e}")

@st.cache_data(ttl=86400) # Cache pour 24h, se rafraîchit si le fichier change ou après 24h
def charger_etat_jardin():
    """Charge l'état du déficit hydrique du jardin depuis un fichier JSON."""
    try:
        with open(ETAT_JARDIN_FILE, 'r', encoding='utf-8') as f:
            etat = json.load(f)
            # Convertir la date en pd.Timestamp pour faciliter les comparaisons
            etat["date_derniere_maj"] = pd.to_datetime(etat["date_derniere_maj"])
            return etat
    except (FileNotFoundError, json.JSONDecodeError):
        # Retourne un état initial si le fichier n'existe pas ou est corrompu
        return {
            "date_derniere_maj": None,
            "deficits_accumules": {}
        }

def sauvegarder_etat_jardin(etat):
    """Sauvegarde l'état du déficit hydrique du jardin dans un fichier JSON."""
    # Convertir la date en chaîne avant de sauvegarder
    if etat["date_derniere_maj"]:
        etat["date_derniere_maj"] = etat["date_derniere_maj"].strftime('%Y-%m-%d')
    with open(ETAT_JARDIN_FILE, 'w', encoding='utf-8') as f:
        json.dump(etat, f, indent=2)
    # Invalider le cache pour que la prochaine lecture prenne la nouvelle valeur
    charger_etat_jardin.clear()

# === 🌿 CONFIGURATION GÉNÉRALE DE LA PAGE ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="centered")
st.title("🌿 Aide au jardinage")

try:
    today = pd.to_datetime(datetime.now().date())
    current_month = str(today.month) # Convertir le mois en chaîne pour correspondre aux clés JSON

    # 🔧 Chargement des recommandations mensuelles (utilisez la nouvelle fonction)
    recommendations_mensuelles = charger_recommandations_mensuelles()

    # 🔧 Chargement des préférences utilisateur (plantes, paillage, sol)
    prefs = charger_preferences_utilisateur()
    plantes_par_defaut = prefs.get("plantes", [])
    paillage_defaut = prefs.get("paillage", False)
    type_sol_defaut = prefs.get("type_sol", "Limoneux")

    # 📚 Chargement des familles de plantes et index
    familles = charger_familles() # Make sure this function is defined
    plantes_index = construire_index_plantes(familles) # Make sure this function is defined

    journal = charger_journal() # Make sure charger_journal is defined as updated previously

    # 🔧 Chargement etat du jardin
    etat_jardin = charger_etat_jardin()
    nouveaux_deficits = {}
    plantes_choisies = plantes_par_defaut
    
    # Définir la date de départ pour le calcul du delta météo
    if etat_jardin["date_derniere_maj"] is None or etat_jardin["date_derniere_maj"] < today - pd.Timedelta(days=METEO_HISTORIQUE_DISPONIBLE):
        # Si pas d'état ou état trop vieux pour les données météo, on repart du dernier arrosage réel ou d'une date récente.
        date_depart_delta_meteo = journal["arrosages"][-1] if journal["arrosages"] else today - pd.Timedelta(days=7)
    else:
        date_depart_delta_meteo = etat_jardin["date_derniere_maj"]

    # Donnez une valeur par défaut générale.
    hauteur_tonte_input_default = 5
    # Tentez de récupérer la dernière hauteur de tonte enregistrée s'il y en a une.
    if journal["tontes"]:
        valid_tontes = [t for t in journal["tontes"] if isinstance(t, dict) and "date" in t]
        if valid_tontes:
            try:
                derniere_tonte_info = max(valid_tontes, key=lambda x: x["date"])
                hauteur_tonte_input_default = derniere_tonte_info.get("hauteur", 5) # Utiliser .get pour une meilleure robustesse
            except ValueError:
                # La liste pourrait être vide ou ne pas contenir d'éléments "max" si elle est mal formée
                pass
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📆 Suivi journalier",
        "💧 Synthèse de mon jardin",
        "📈 Suivi Météo",
        "📊 Mon Jardin en chiffre",
        "🌱 Mon Potager & Paramètres"
    ])

    with tab1:
        st.header("📆 Suivi du Jour")

        st.markdown("### Actions Rapides")

        col_arrosage, col_tonte = st.columns(2)

        with col_arrosage:
            if st.button("💧 J'ai arrosé aujourd'hui", use_container_width=True):
                journal["arrosages"].append(today)
                sauvegarder_journal(journal)
                if "deficits_accumules" not in etat_jardin:
                    etat_jardin["deficits_accumules"] = {}
                for plante_id in plantes_choisies:
                    if plante_id in etat_jardin["deficits_accumules"]:
                        etat_jardin["deficits_accumules"][plante_id] = 0.0
                sauvegarder_etat_jardin(etat_jardin)
                st.success("💧 Arrosage enregistré ! Le déficit des plantes concernées a été mis à jour.")
                st.rerun()

        with col_tonte:
            hauteur_tonte_input = st.slider("Hauteur après tonte (cm) :", 2, 10, hauteur_tonte_input_default, key="daily_tonte_hauteur")
            if st.button("✂️ J'ai tondu aujourd'hui", use_container_width=True):
                journal["tontes"].append({"date": today, "hauteur": hauteur_tonte_input})
                sauvegarder_journal(journal)
                st.success(f"✂️ Tonte enregistrée à {hauteur_tonte_input} cm.")
                st.rerun()

        st.markdown("---")
        st.markdown("### Votre Historique Rapide")

        if journal["arrosages"]:
            st.info(f"**Dernier arrosage :** {format_date(journal['arrosages'][-1].date(), format='full', locale='fr')}")
        else:
            st.info("**Aucun arrosage enregistré pour l'instant.**")

        if journal["tontes"]:
            valid_tontes = [tonte for tonte in journal["tontes"] if isinstance(tonte, dict) and "date" in tonte and isinstance(tonte["date"], pd.Timestamp)]
            if valid_tontes:
                derniere_tonte = max(valid_tontes, key=lambda x: x["date"])
                st.info(f"**Dernière tonte :** {format_date(derniere_tonte['date'].date(), format='full', locale='fr')} à {derniere_tonte['hauteur']} cm")
            else:
                st.warning("**Aucune tonte valide enregistrée.**")
        else:
            st.info("**Aucune tonte enregistrée pour l'instant.**")

    with tab5:
        st.header("🌱 Mon Potager & Paramètres")

        # Sélection des plantes cultivées
        toutes_les_plantes = sorted(plantes_index.keys())
        plantes_choisies = st.multiselect(
            "Sélectionnez les **plantes cultivées** :",
            toutes_les_plantes,
            default=plantes_par_defaut,
            key="plantes_selection_tab5" # Clé unique pour éviter les conflits
        )

        # Bouton de réinitialisation des paramètres
        if st.button("🔁 Réinitialiser les paramètres", key="reset_prefs_tab5"):
            enregistrer_preferences_utilisateur({})
            st.success("Paramètres réinitialisés ! Actualisation de la page...")
            st.experimental_rerun()

        st.markdown("---")
        st.subheader("📍 Lieu et Météo")

        # Champ de texte pour la ville
        ville = st.text_input("Ville ou commune (ex: Beauzelle) :", "Beauzelle", key="ville_input_tab5")
        infos_ville = get_coords_from_city(ville)

        if infos_ville:
            LAT = infos_ville["lat"]
            LON = infos_ville["lon"]
            st.info(f"📍 Ville sélectionnée : **{infos_ville['name']}**, {infos_ville['country']} \n"
                                f"🌐 Coordonnées : `{LAT:.2f}, {LON:.2f}`")
        else:
            st.error("❌ Ville non trouvée. Veuillez vérifier l'orthographe ou en choisir une autre.")
            st.stop() # Arrête l'exécution pour éviter des erreurs si la ville n'est pas trouvée

        # Récupération des données météo pour cette ville
        df = recuperer_meteo(LAT, LON)
        # Note: df["jour"] n'est pas directement utilisé dans tab5, mais utile pour d'autres onglets
        df["jour"] = df["date"].dt.strftime("%d/%m")

        st.markdown("---")
        st.subheader("🌍 Caractéristiques de votre sol")

        # Sélection du type de sol
        type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"],
                                    index=["Limoneux", "Sableux", "Argileux"].index(type_sol_defaut),
                                    key="type_sol_select_tab5")

        # Case à cocher pour le paillage
        paillage = st.checkbox("Présence de paillage", value=paillage_defaut, key="paillage_checkbox_tab5")

        # Enregistrement des préférences
        prefs.update({"plantes": plantes_choisies, "paillage": paillage, "type_sol": type_sol})
        enregistrer_preferences_utilisateur(prefs)
        st.success("Vos préférences ont été enregistrées.")


        st.markdown("---")
        st.subheader("💧 Historique Arrosage")

        # Affichage du dernier arrosage enregistré ou slider si aucun
        if journal["arrosages"]:
            # Utilisation d'un nom de variable local pour éviter toute confusion avec d'autres onglets
            date_dernier_arrosage_tab5 = journal["arrosages"][-1]
            jours_depuis_tab5 = (today - date_dernier_arrosage_tab5).days
            st.markdown(f"💧 **Dernier arrosage enregistré :** il y a **{jours_depuis_tab5} jour(s)** (le {date_dernier_arrosage_tab5.strftime('%d/%m/%Y')})")
        else:
            # Slider pour simuler la dernière date d'arrosage si le journal est vide
            jours_depuis_tab5 = st.slider("Jours depuis le dernier arrosage (pour simulation si aucun enregistré) :", 0, 14, 3, key="jours_arrosage_slider_tab5")
            date_dernier_arrosage_tab5 = today - pd.Timedelta(days=jours_depuis_tab5)
            st.info(f"Simule le dernier arrosage au **{date_dernier_arrosage_tab5.strftime('%d/%m/%Y')}**.")


        # Calculs des facteurs de sol et paillage et seuils de déficit
        # Ces variables sont réutilisées par d'autres parties de l'application
        facteur_sol = {"Sableux": 1.3, "Limoneux": 1.0, "Argileux": 0.9}.get(type_sol, 1.0)
        facteur_paillage = 0.7 if paillage else 1.0
        SEUILS_DEFICIT_SOL = {"Sableux": 10, "Limoneux": 20, "Argileux": 30}
        SEUIL_DEFICIT = SEUILS_DEFICIT_SOL.get(type_sol, 20)

        st.caption(f"Le seuil de déficit pour un sol **{type_sol.lower()}** est de **{SEUIL_DEFICIT} mm** (quantité d'eau manquante avant arrosage critique).")


        st.markdown("---")
        st.subheader("✂️ Historique Tonte")

        # Affichage de la dernière tonte enregistrée ou slider si aucune
        if journal["tontes"]:
            # Récupérer la dernière tonte valide
            valid_tontes_tab5 = [t for t in journal["tontes"] if isinstance(t, dict) and "date" in t]
            if valid_tontes_tab5:
                date_dernier_tonte_tab5 = max(valid_tontes_tab5, key=lambda x: x["date"])["date"]
                jours_depuis_tonte_tab5 = (today - date_dernier_tonte_tab5).days
                st.markdown(f"✂️ **Dernière tonte enregistrée :** il y a **{jours_depuis_tonte_tab5} jour(s)** (le {date_dernier_tonte_tab5.strftime('%d/%m/%Y')})")
            else:
                jours_depuis_tonte_tab5 = st.slider("Jours depuis la dernière tonte (pour simulation si aucune enregistrée) :", 1, 21, 7, key="jours_tonte_slider_tab5_empty")
                date_dernier_tonte_tab5 = today - pd.Timedelta(days=jours_depuis_tonte_tab5)
                st.info(f"Simule la dernière tonte au **{date_dernier_tonte_tab5.strftime('%d/%m/%Y')}**.")
        else:
            # Slider pour simuler la dernière date de tonte si le journal est vide
            jours_depuis_tonte_tab5 = st.slider("Jours depuis la dernière tonte (pour simulation si aucune enregistrée) :", 1, 21, 7, key="jours_tonte_slider_tab5")
            date_dernier_tonte_tab5 = today - pd.Timedelta(days=jours_depuis_tonte_tab5)
            st.info(f"Simule la dernière tonte au **{date_dernier_tonte_tab5.strftime('%d/%m/%Y')}**.")

        # Slider pour la hauteur cible de la pelouse
        hauteur_cible_cm = st.slider("Hauteur cible de votre pelouse (cm) :", 3, 8, 5, key="hauteur_cible_slider_tab5")
        st.caption(f"Vous visez une hauteur de coupe de **{hauteur_cible_cm} cm** pour votre pelouse.")

        # Le DataFrame df_tonte_tab5 est créé ici mais est souvent utilisé dans des calculs globaux ou d'autres onglets
        # Assurez-vous que df est bien défini par recuperer_meteo qui est appelée plus haut
        df_tonte_tab5 = df[(df["date"] >= date_dernier_tonte_tab5) & (df["date"] <= today)].copy()


    # 📈 Calcul de croissance de l’herbe depuis la dernière tonte
    # Make sure croissance_herbe is defined
    df_tonte_tab5["croissance"] = df_tonte_tab5.apply(
        lambda row: croissance_herbe(row["temp_max"], row["pluie"], row["evapo"]), axis=1
    )
    croissance_totale_mm = df_tonte_tab5["croissance"].sum()

    # Ensure hauteur_initiale is correctly pulled from journal if available
    hauteur_initiale = journal["tontes"][-1]["hauteur"] if journal["tontes"] else hauteur_tonte_input
    hauteur_estimee_cm = hauteur_initiale + (croissance_totale_mm / 10)

    # 🔥 Alerte chaleur et pluie
    df_futur = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=3))]
    jours_chauds_a_venir = (df_futur["temp_max"] >= 30).sum()
    pluie_prochaine_48h = df_futur.head(2)["pluie"].sum()


    # Calcul des déficits pour le jour actuel, basé sur l'état précédent
    for code_famille, infos_famille in familles.items():
        # Pour chaque famille de plante (qui a un KC unique)
        kc = infos_famille["kc"]
        
        # Récupérer le déficit de la veille pour cette plante, ou 0 si non trouvé
        deficit_hier = etat_jardin["deficits_accumules"].get(code_famille, 0.0)

        # Calcul du bilan hydrique uniquement pour la période entre date_depart_delta_meteo et today
        # Assurez-vous que df contient bien cette période !
        df_periode = df[(df["date"] >= date_depart_delta_meteo) & (df["date"] <= today)]

        # Si l'arrosage a eu lieu entre date_depart_delta_meteo et today, le déficit est réinitialisé à ce moment
        # Pour simplifier, si un arrosage est enregistré aujourd'hui, on le met à zéro.
        # Sinon, on le calcule.
        
        # On recalcule le bilan hydrique depuis date_depart_delta_meteo
        pluie_delta = df_periode["pluie"].sum()
        et0_delta = df_periode["evapo"].sum()
        besoin_delta = et0_delta * kc * facteur_sol * facteur_paillage
        
        bilan_periode = pluie_delta - besoin_delta
        
        # Le nouveau déficit est l'ancien déficit + le bilan de la période
        # Ne pas laisser le déficit devenir négatif (excédent)
        nouveau_deficit = max(0.0, deficit_hier - bilan_periode) # - bilan car déficit est négatif du bilan

        nouveaux_deficits[code_famille] = nouveau_deficit

    # Mettre à jour l'état du jardin avec les déficits calculés aujourd'hui
    etat_jardin["date_derniere_maj"] = today
    etat_jardin["deficits_accumules"] = nouveaux_deficits
    sauvegarder_etat_jardin(etat_jardin)

    # === 💡 CALCUL DES RECOMMANDATIONS PAR PLANTE ===
    table_data = []

    # Calcul de la pluie sur les prochaines 24h et 48h
    # Note : today est déjà un pd.Timestamp, donc today + pd.Timedelta(days=1) est demain
    pluie_prochaine_24h = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=1))]["pluie"].sum()
    pluie_prochaine_48h = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=2))]["pluie"].sum()

    for code_famille, infos_famille in familles.items():
        plantes_famille = infos_famille["plantes"]
        if not any(p in plantes_choisies for p in plantes_famille):
            continue

        kc = infos_famille["kc"]
        plantes_affichees = [p.capitalize() for p in plantes_famille if p in plantes_choisies]
        nom_affiche = ", ".join(plantes_affichees)

        # Maintenant, on utilise le déficit CALCULÉ et SAUVEGARDÉ pour aujourd'hui
        deficit = nouveaux_deficits.get(code_famille, 0.0)

        # date_dernier_arrosage will be a pd.Timestamp
        date_dernier_arrosage_for_calc = journal["arrosages"][-1] if journal["arrosages"] else today - pd.Timedelta(days=7)
        df_passe = df[(df["date"] > date_dernier_arrosage_for_calc) & (df["date"] <= today)]

        pluie_totale = df_passe["pluie"].sum()
        et0_total = df_passe["evapo"].sum()
        besoin_total = et0_total * kc * facteur_sol * facteur_paillage
        bilan = pluie_totale - besoin_total
        deficit = max(-bilan, 0)
        #pluie_prochaine = df_futur["pluie"].sum()

        if deficit == 0:
            besoin, infos_bilan = False, f"✅ Excédent : {bilan:.1f} mm"
        elif deficit <= SEUIL_DEFICIT * 0.25: # Si le déficit est inférieur à 25% du seuil, c'est léger, pas besoin
            besoin, infos_bilan = False, f"🤏 Déficit très léger : {deficit:.1f} mm"
        elif deficit <= SEUIL_DEFICIT:
            # Si le déficit est léger mais > 25% du seuil, on regarde la pluie sur 24h
            if pluie_prochaine_24h >= deficit:
                besoin, infos_bilan = False, f"🌧️ Pluie prévue ({pluie_prochaine_24h:.1f} mm) dans 24h compensera"
            else:
                besoin, infos_bilan = False, f"🤏 Déficit léger : {deficit:.1f} mm" # On considère toujours que c'est léger si <= seuil

        # Le cas où le déficit est significatif (dépasse le SEUIL_DEFICIT)
        else: # deficit > SEUIL_DEFICIT
            # On regarde si la pluie dans les prochaines 48h peut compenser
            if pluie_prochaine_48h >= deficit:
                # Retarder l'arrosage si la pluie des 48h compense ET que le déficit n'est pas trop grand (ex: pas plus de 125% du seuil)
                # Cette condition est un peu subjective, à ajuster selon votre tolérance au stress
                if deficit <= SEUIL_DEFICIT * 1.25: # Tolérance de 25% au-delà du seuil pour attendre la pluie
                    besoin, infos_bilan = False, f"🌧️ Pluie prévue ({pluie_prochaine_48h:.1f} mm) dans 48h compensera (Déficit actuel: {deficit:.1f} mm)"
                else: # Le déficit est trop important pour attendre 48h, même avec pluie
                    besoin, infos_bilan = True, f"💧 Déficit critique : {deficit:.1f} mm (Pluie 48h: {pluie_prochaine_48h:.1f} mm)"
            else: # Pas de pluie suffisante prévue
                besoin, infos_bilan = True, f"💧 Déficit : {deficit:.1f} mm"

        table_data.append({
             "Plante": nom_affiche,
             "Recommandation": "Arroser" if besoin else "Pas besoin",
             "Couleur": "🟧" if besoin else "🟦",
             "Détail": infos_bilan
         })

    with tab2 :
        st.header("💧 Synthèse de mon Jardin")

        # Météo du Jour et Alertes (en haut)
        st.markdown("### Météo Actuelle & Alertes")
        meteo_auj = df[df["date"] == today]
        if not meteo_auj.empty:
            temp = meteo_auj["temp_max"].values[0]
            pluie = meteo_auj["pluie"].values[0]

            # Utilisation de st.columns pour un affichage côte à côte des métriques
            col_meteo1, col_meteo2 = st.columns(2)
            with col_meteo1:
                st.metric(label="🌡️ Température Max Aujourd'hui", value=f"{temp}°C")
            with col_meteo2:
                st.metric(label="🌧️ Précipitations Aujourd'hui", value=f"{pluie:.1f} mm")

        if jours_chauds_a_venir >= 2:
            st.warning(f"🔥 **Alerte Chaleur :** {jours_chauds_a_venir} jour(s) avec ≥30°C à venir ! Pensez à l'hydratation.")
        if pluie_prochaine_48h >= 10:
            st.info(f"🌧️ **Bonne nouvelle :** {pluie_prochaine_48h:.1f} mm de pluie attendus dans les 48h. Peut-être pas besoin d'arroser !")

        st.markdown("---") # Séparateur visuel

        # Recommandations Générales (Arrosage, Tonte)
        st.markdown("### Recommandations Générales")
        col_reco1, col_reco2 = st.columns(2)

        with col_reco1:
            if any(p["Recommandation"] == "Arroser" for p in table_data):
                nb_plantes_a_arroser = sum(1 for p in table_data if p["Recommandation"] == "Arroser")
                st.error(f"💧 **Urgent ! {nb_plantes_a_arroser} plante(s) à arroser** aujourd'hui.")
            else:
                st.success("✅ **Pas besoin d'arroser** aujourd'hui.")

        with col_reco2:
            seuil_tonte_cm = hauteur_initiale * 1.5
            if hauteur_estimee_cm >= seuil_tonte_cm:
                st.warning(f"✂️ **Tonte recommandée :** Gazon estimé à {hauteur_estimee_cm:.1f} cm (cible {hauteur_cible_cm} cm).")
            else:
                st.success(f"🌱 **Pas besoin de tondre :** Gazon estimé à {hauteur_estimee_cm:.1f} cm (cible {hauteur_cible_cm} cm).")

        st.markdown("---")

        # Recommandations Détaillées par Plante
        st.markdown("### 🌱 Recommandations par Plante")
        for ligne in table_data:
            color_code = "#F8D7DA" if ligne["Recommandation"] == "Arroser" else "#D4EDDA" # Rouge pâle pour Arroser, Vert pâle pour Pas besoin
            emoji = "💧" if ligne["Recommandation"] == "Arroser" else "✅"
            st.markdown(f"<div style='background-color: {color_code}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                        f"{emoji} <b>{ligne['Plante']}</b> : {ligne['Recommandation']} – {ligne['Détail']}</div>",
                        unsafe_allow_html=True)

        st.markdown("---")

        # Prévisions
        st.markdown("### 📅 Prévisions du Potager")
        col_pred1, col_pred2 = st.columns(2)

        with col_pred1:
            arrosage_necessaire_aujourdhui = any(p["Recommandation"] == "Arroser" for p in table_data)
            if arrosage_necessaire_aujourdhui:
                st.warning("💧 **Arrosage nécessaire aujourd'hui** pour certaines plantes.")
            else:
                date_prochain_arrosage = estimer_arrosage_le_plus_contraignant(
                    df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=7))], # Limiter la prévision
                    plantes_choisies, plantes_index, SEUIL_DEFICIT, facteur_sol, facteur_paillage
                )
                if date_prochain_arrosage:
                    nb_jours = (date_prochain_arrosage - today).days
                    message_jours = "aujourd'hui" if nb_jours == 0 else ("demain" if nb_jours == 1 else f"dans {nb_jours} jour(s)")
                    st.info(f"💧 **Prochain arrosage estimé :** {message_jours} ({format_date(date_prochain_arrosage.date(), format='medium', locale='fr')})")
                else:
                    st.success("✅ **Pas d'arrosage nécessaire** dans les 7 prochains jours.")

        with col_pred2:
            date_prochaine_tonte = estimer_date_prochaine_tonte(df[df["date"] > today], hauteur_estimee_cm, hauteur_cible_cm)
            if date_prochaine_tonte:
                st.info(f"✂️ **Prochaine tonte estimée :** {format_date(date_prochaine_tonte.date(), format='medium', locale='fr')}")
            else:
                st.success("🟢 **Pas de tonte prévue** dans les prochains jours.")

    with tab3:
        st.header("📈 Suivi Météo")
        st.markdown("Visualisez les données météorologiques pour votre ville.")

        # Affichez la ville sélectionnée en haut pour rappel
        if infos_ville:
            st.subheader(f"Météo pour {infos_ville['name']} ({infos_ville['country']})")
        
        st.markdown("---")
        st.markdown("### Prévisions Quotidiennes")

        df_a_afficher = df[(df["date"] >= today - pd.Timedelta(days=2)) & (df["date"] <= today + pd.Timedelta(days=7))]
        for _, row in df_a_afficher.iterrows():
            jour_texte = "Aujourd'hui" if row["date"].date() == today.date() else format_date(row["date"].date(), format='full', locale='fr')
            # Utilisez une icône météo simple basée sur les conditions (ex: soleil, pluie, nuage)
            # Ceci est un exemple, vous devrez peut-être étendre avec une vraie logique d'icônes météo
            icone_meteo = "☀️" if row["temp_max"] > 25 and row["pluie"] < 1 else ("🌧️" if row["pluie"] > 0 else "☁️")

            st.markdown(f"""
            <div style="background-color: {'#e0f7fa' if row['date'].date() == today.date() else '#f0f8ff'}; 
                        border-left: 5px solid {'#007bff' if row['date'].date() == today.date() else '#ccc'};
                        border-radius: 8px; padding: 10px; margin-bottom: 8px;
                        display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <b>{jour_texte}</b><br>
                    <small>{format_date(row["date"].date(), format='dd MMM', locale='fr')}</small>
                </div>
                <div style="text-align: right;">
                    {icone_meteo} 🌡️ {row['temp_max']}°C<br>
                    💧 {row['pluie']:.1f} mm &nbsp; 🌬️ {int(row['vent']) if pd.notna(row['vent']) else '-'} km/h
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Calcul des statistiques
    stats_arrosage = calculer_stats_arrosage(journal)
    stats_tonte = calculer_stats_tonte(journal)

    with tab4:
        st.header("📊 Historique & Statistiques du Jardin")

        st.markdown("### Calendrier de Votre Activité")
        afficher_calendrier_frise(journal, today) # Cette fonction est clé ici

        st.markdown("---")

        st.markdown("### Aperçu Rapide de Votre Suivi")
        col_arrosage, col_tonte = st.columns(2)

        with col_arrosage:
            st.markdown("#### 💧 Arrosages")
            st.metric(label="Total", value=stats_arrosage["nb_arrosages"])
            st.metric(label="Fréquence Moyenne", value=f"{stats_arrosage['freq_moyenne_jours']} jours")
            if stats_arrosage["dernier_arrosage_date"]:
                st.caption(f"Dernier : {format_date(stats_arrosage['dernier_arrosage_date'], format='medium', locale='fr')}")

        with col_tonte:
            st.markdown("#### ✂️ Tontes")
            st.metric(label="Total", value=stats_tonte["nb_tontes"])
            st.metric(label="Fréquence Moyenne", value=f"{stats_tonte['freq_moyenne_jours']} jours")
            st.metric(label="Hauteur Moyenne", value=f"{stats_tonte['hauteur_moyenne']} cm")
            if stats_tonte["derniere_tonte_date"]:
                st.caption(f"Dernière : {format_date(stats_tonte['derniere_tonte_date'], format='medium', locale='fr')}")

        st.markdown("---")

        st.markdown("### 📝 Recommandations Mensuelles")
        reco_mois = recommendations_mensuelles.get(int(current_month))

        if reco_mois:
            st.subheader(f"{reco_mois['titre']} du mois")
            st.write("Voici quelques conseils pour votre jardin ce mois-ci :")
            for conseil in reco_mois["conseils"]:
                st.markdown(f"- {conseil}")
        else:
            st.info("Aucune recommandation spécifique disponible pour ce mois. Revenez le mois prochain !")

        with st.expander("📈 Voir les statistiques avancées"):
            st.write("Ici, vous pourriez ajouter des graphiques plus détaillés ou d'autres statistiques pertinentes sur l'évolution de votre jardin.")
            # Ex: st.line_chart(df_arrosage_sur_annee)
            # Ex: st.bar_chart(df_hauteur_tonte_mois)

except Exception as e:
    st.error(f"❌ Erreur générale de l'application : {e}")