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

# 🌍 Localisation en français pour les dates
#locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")

# === Chemins de base ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAM_PATH = os.path.join(BASE_DIR, "parametres_utilisateur.json")
JOURNAL_PATH = os.path.join(BASE_DIR, "journal_jardin.json")

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

# === Météo : géocodage d'une ville vers latitude/longitude ===
@st.cache_data(ttl=3600)
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
@st.cache_data(ttl=3600)
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

# === 🌿 CONFIGURATION GÉNÉRALE DE LA PAGE ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="centered")
st.title("🌿 Aide au jardinage")

try:
    today = pd.to_datetime(datetime.now().date())

    # 🔧 Chargement des préférences utilisateur (plantes, paillage, sol)
    prefs = charger_preferences_utilisateur()
    plantes_par_defaut = prefs.get("plantes", [])
    paillage_defaut = prefs.get("paillage", False)
    type_sol_defaut = prefs.get("type_sol", "Limoneux")

    # 📚 Chargement des familles de plantes et index
    familles = charger_familles() # Make sure this function is defined
    plantes_index = construire_index_plantes(familles) # Make sure this function is defined

    journal = charger_journal() # Make sure charger_journal is defined as updated previously

    # === 📆 SUIVI JOURNALIER ===
    with st.expander("📆 Suivi journalier", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            if st.button("✅ J’ai arrosé aujourd’hui"):
                # Always append a pd.Timestamp
                journal["arrosages"].append(today)
                sauvegarder_journal(journal) # Make sure sauvegarder_journal is defined as updated previously
                st.success("💧 Arrosage enregistré.")

        with col2:
            hauteur_tonte_input = st.slider("Hauteur après tonte (cm) :", 2, 10, 5)
            if st.button("✂️ J’ai tondu aujourd’hui"):
                # Always store pd.Timestamp
                journal["tontes"].append({
                    "date": today,
                    "hauteur": hauteur_tonte_input
                })
                sauvegarder_journal(journal)
                st.success(f"✂️ Tonte enregistrée à {hauteur_tonte_input} cm.")

        # Displaying dates from journal (they should now be pd.Timestamps)
        # --- Start of correct display block ---
        if journal["arrosages"]:
            # Use .date() to get a datetime.date object for format_date
            st.markdown(f"**Dernier arrosage enregistré :** {format_date(journal['arrosages'][-1].date(), format='full', locale='fr')}")

        if journal["tontes"]:
            derniere_tonte = max(journal["tontes"], key=lambda x: x["date"])
            # Use .date() for display
            st.write(f"**Dernière date de tonte :** {format_date(derniere_tonte['date'].date(), format='full', locale='fr')}")
            st.write(f"**Hauteur de coupe :** {derniere_tonte['hauteur']} cm")
        else:
            st.write("**Aucune tonte enregistrée.**")
        # --- End of correct display block ---

        # The following block is a duplicate and was causing inconsistent display.
        # It's removed to ensure dates are always formatted correctly.
        # if journal["arrosages"]:
        #     st.markdown(f"**Dernier arrosage enregistré :** {journal['arrosages'][-1]}")
        # if journal["tontes"]:
        #     derniere_tonte = max(journal["tontes"], key=lambda x: x["date"])
        #     st.write(f"**Dernière date de tonte :** {derniere_tonte['date']}")
        #     st.write(f"**Hauteur de coupe :** {derniere_tonte['hauteur']} cm")
        # else:
        #     st.write("**Aucune tonte enregistrée.**")

    # === 🌱 SÉLECTION DU POTAGER ===
    with st.expander("🌱 Mon potager", expanded=False):
        toutes_les_plantes = sorted(plantes_index.keys())
        plantes_choisies = st.multiselect(
            "Sélectionnez les plantes cultivées :",
            toutes_les_plantes,
            default=plantes_par_defaut
        )
        if st.button("🔁 Réinitialiser les paramètres"):
            enregistrer_preferences_utilisateur({}) # Make sure this function is defined
            st.experimental_rerun()

    # === ⚙️ PARAMÈTRES DU JARDIN ===
    with st.expander("🛠️ Paramètres de votre jardin", expanded=False):
        ville = st.text_input("Ville ou commune :", "Beauzelle")
        infos_ville = get_coords_from_city(ville) # Make sure this function is defined

        if infos_ville:
            LAT = infos_ville["lat"]
            LON = infos_ville["lon"]
            st.markdown(f"📍 Ville sélectionnée : **{infos_ville['name']}**, {infos_ville['country']} \n"
                        f"🌐 Coordonnées : {LAT:.2f}, {LON:.2f}")
        else:
            st.error("❌ Ville non trouvée.")
            st.stop()

        type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"],
                                 index=["Limoneux", "Sableux", "Argileux"].index(type_sol_defaut))
        paillage = st.checkbox("Présence de paillage", value=paillage_defaut)

        # 💾 Enregistrement des préférences mises à jour
        prefs.update({"plantes": plantes_choisies, "paillage": paillage, "type_sol": type_sol})
        enregistrer_preferences_utilisateur(prefs)

    # === 📊 RÉCUPÉRATION MÉTÉO ===
    df = recuperer_meteo(LAT, LON) # Make sure this function is defined
    df["jour"] = df["date"].dt.strftime("%d/%m")

    # === ✂️ TONTE DE LA PELOUSE ===
    with st.expander("✂️ Tonte de la pelouse", expanded=False):
        if journal["tontes"]:
            # On prend la dernière tonte, which should already be a pd.Timestamp from charger_journal
            date_dernier_tonte = max(journal["tontes"], key=lambda x: x["date"])["date"] # Ensure this is pd.Timestamp
            jours_depuis_tonte = (today - date_dernier_tonte).days
            st.markdown(f"✂️ Dernière tonte enregistrée : il y a **{jours_depuis_tonte} jour(s)**")
        else:
            jours_depuis_tonte = st.slider("Jours depuis la dernière tonte :", 1, 21, 7)
            date_dernier_tonte = today - pd.Timedelta(days=jours_depuis_tonte) # Ensure this is also a Timestamp

        hauteur_cible_cm = st.slider("Hauteur cible de pelouse (cm) :", 3, 8, 5)
        # df_tonte should include dates up to 'today' (a Timestamp)
        df_tonte = df[(df["date"] >= date_dernier_tonte) & (df["date"] <= today)].copy()

        #st.markdown("### 📈 Suivi visuel de la hauteur de pelouse")
        #afficher_evolution_pelouse(journal, df, today) # Make sure this function is defined

    # 📈 Calcul de croissance de l’herbe depuis la dernière tonte
    # Make sure croissance_herbe is defined
    df_tonte["croissance"] = df_tonte.apply(
        lambda row: croissance_herbe(row["temp_max"], row["pluie"], row["evapo"]), axis=1
    )
    croissance_totale_mm = df_tonte["croissance"].sum()

    # Ensure hauteur_initiale is correctly pulled from journal if available
    hauteur_initiale = journal["tontes"][-1]["hauteur"] if journal["tontes"] else hauteur_tonte_input
    hauteur_estimee_cm = hauteur_initiale + (croissance_totale_mm / 10)

    # 🔥 Alerte chaleur et pluie
    df_futur = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=3))]
    jours_chauds_a_venir = (df_futur["temp_max"] >= 30).sum()
    pluie_prochaine_48h = df_futur.head(2)["pluie"].sum()

    # === 💧 CALCUL BESOINS EN ARROSAGE ===
    with st.expander("💧 Arrosage", expanded=False):
        if journal["arrosages"]:
            # journal["arrosages"][-1] is already a pd.Timestamp
            date_dernier_arrosage = journal["arrosages"][-1]
            jours_depuis = (today - date_dernier_arrosage).days
            st.markdown(f"💧 Dernier arrosage : il y a **{jours_depuis} jour(s)**")
        else:
            jours_depuis = st.slider("Jours depuis le dernier arrosage :", 0, 14, 3)
            # Ensure this calculated date is also a Timestamp
            date_dernier_arrosage = today - pd.Timedelta(days=jours_depuis)

        facteur_sol = {"Sableux": 1.3, "Limoneux": 1.0, "Argileux": 0.9}.get(type_sol, 1.0)
        facteur_paillage = 0.7 if paillage else 1.0
        SEUILS_DEFICIT_SOL = {"Sableux": 10, "Limoneux": 20, "Argileux": 30}
        SEUIL_DEFICIT = SEUILS_DEFICIT_SOL.get(type_sol, 20)

        st.caption(f"💧 Seuil de déficit ({type_sol.lower()}) : {SEUIL_DEFICIT} mm")

    # === 💡 CALCUL DES RECOMMANDATIONS PAR PLANTE ===
    table_data = []

    for code_famille, infos_famille in familles.items():
        plantes_famille = infos_famille["plantes"]
        if not any(p in plantes_choisies for p in plantes_famille):
            continue  # aucune plante de cette famille

        kc = infos_famille["kc"]
        plantes_affichees = [p.capitalize() for p in plantes_famille if p in plantes_choisies]
        nom_affiche = ", ".join(plantes_affichees)

        # date_dernier_arrosage will be a pd.Timestamp
        date_dernier_arrosage_for_calc = journal["arrosages"][-1] if journal["arrosages"] else today - pd.Timedelta(days=7)
        df_passe = df[(df["date"] > date_dernier_arrosage_for_calc) & (df["date"] <= today)]

        pluie_totale = df_passe["pluie"].sum()
        et0_total = df_passe["evapo"].sum()
        besoin_total = et0_total * kc * facteur_sol * facteur_paillage
        bilan = pluie_totale - besoin_total
        deficit = max(-bilan, 0)
        pluie_prochaine = df_futur["pluie"].sum()

        if deficit == 0:
            besoin, infos_bilan = False, f"✅ Excédent : {bilan:.1f} mm"
        elif deficit <= SEUIL_DEFICIT:
            besoin, infos_bilan = False, f"🤏 Déficit léger : {deficit:.1f} mm"
        elif pluie_prochaine >= deficit:
            besoin, infos_bilan = False, f"🌧️ Pluie prévue ({pluie_prochaine:.1f} mm) compensera"
        else:
            besoin, infos_bilan = True, f"💧 Déficit : {deficit:.1f} mm"

        table_data.append({
            "Plante": nom_affiche,
            "Recommandation": "Arroser" if besoin else "Pas besoin",
            "Couleur": "🟧" if besoin else "🟦",
            "Détail": infos_bilan
        })

    # === 🔍 SYNTHÈSE RAPIDE DU JOUR ===
    st.markdown("### 🔍 Résumé du jour")

    # 🔍 Données météo du jour
    meteo_auj = df[df["date"] == today] # 'today' is a pd.Timestamp here
    if not meteo_auj.empty:
        temp = meteo_auj["temp_max"].values[0]
        pluie = meteo_auj["pluie"].values[0]

        meteo_html = f"""
        <div style='padding:10px; background-color:#f8f9fa; border-radius:6px; margin-bottom:10px;'>
            <p>🌡️ <b>Température max :</b> {temp}°C</p>
            <p>🌧️ <b>Précipitations :</b> {pluie:.1f} mm</p>
        </div>
        """
        st.markdown(meteo_html, unsafe_allow_html=True)

    # 🔥 Alerte chaleur
    if jours_chauds_a_venir >= 2:
        st.warning(f"🔥 **{jours_chauds_a_venir} jour(s) ≥30°C à venir**")

    # 🌧️ Pluie à venir
    if pluie_prochaine_48h >= 10:
        st.markdown(f"""
        <div style='background-color:#d1ecf1; padding:10px; border-radius:6px; margin-bottom:10px;'>
            🌧️ <b>{pluie_prochaine_48h:.1f} mm de pluie dans les 48h</b>
        </div>
        """, unsafe_allow_html=True)

    # 💧 Arrosage
    if any(p["Recommandation"] == "Arroser" for p in table_data):
        nb = sum(p["Recommandation"] == "Arroser" for p in table_data)
        st.markdown(f"""
        <div style='background-color:#f8d7da; padding:10px; border-radius:6px; margin-bottom:10px;'>
            💧 <b>{nb} plante(s) à arroser aujourd’hui</b>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='background-color:#d4edda; padding:10px; border-radius:6px; margin-bottom:10px;'>
            ✅ <b>Aucune plante à arroser</b>
        </div>
        """, unsafe_allow_html=True)

    # ✂️ Tonte
    seuil_tonte_cm = hauteur_initiale * 1.5

    if hauteur_estimee_cm >= seuil_tonte_cm:
        st.markdown("""
        <div style='background-color:#fff3cd; padding:10px; border-radius:6px; margin-bottom:10px;'>
            ✂️ <b>Tonte recommandée :</b> la hauteur dépasse le seuil conseillé
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='background-color:#d4edda; padding:10px; border-radius:6px; margin-bottom:10px;'>
            ✅ <b>Pas besoin de tondre actuellement</b>
        </div>
        """, unsafe_allow_html=True)

    # 📏 Hauteur actuelle
    st.markdown(f"""
    <p style='margin-top:10px;'>
    📏 <b>Hauteur de gazon estimée actuelle :</b> {hauteur_estimee_cm:.1f} cm
    </p>
    """, unsafe_allow_html=True)


    # === 🌱 AFFICHAGE DES RECOMMANDATIONS PAR PLANTE ===
    st.markdown("## 🌱 Recommandations détaillées")
    for ligne in table_data:
        color = "#F8C17E" if ligne["Couleur"] == "🟧" else "#9EF89E"
        emoji = "💧" if ligne["Recommandation"] == "Arroser" else "✅"
        st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                    f"{emoji} <b>{ligne['Plante']}</b> : {ligne['Recommandation']} – {ligne['Détail']}</div>",
                    unsafe_allow_html=True)

    # === 📅 LES PREVISIONS ===
    st.markdown("### 📅 Prévisions du potager et météo")
    # 📅 Prochain arrosage estimé (le plus urgent)
    # Ensure estimer_arrosage_le_plus_contraignant returns a pd.Timestamp
    date_prochain_arrosage = estimer_arrosage_le_plus_contraignant(
        df[df["date"] > today],
        plantes_choisies,
        plantes_index,
        SEUIL_DEFICIT,
        facteur_sol,
        facteur_paillage
    )

    if date_prochain_arrosage:
        nb_jours = (date_prochain_arrosage - today).days
        st.markdown(f"""
        <div style='background-color:#fff3cd; padding:10px; border-radius:6px; margin-bottom:10px;'>
            💧 <b>Prochain arrosage estimé :</b> dans {nb_jours} jour(s)<br>
            📆 <i>{format_date(date_prochain_arrosage.date(), format='full', locale='fr')}</i>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='background-color:#d4edda; padding:10px; border-radius:6px; margin-bottom:10px;'>
            ✅ <b>Aucun arrosage estimé nécessaire dans les prochains jours</b>
        </div>
        """, unsafe_allow_html=True)

    # 📅 Estimation de la prochaine tonte
    df_futur_tonte = df[df["date"] > today]
    # Ensure estimer_date_prochaine_tonte returns a pd.Timestamp
    date_prochaine_tonte = estimer_date_prochaine_tonte(df_futur_tonte, hauteur_estimee_cm, hauteur_cible_cm)

    if date_prochaine_tonte:
        st.markdown(f"""
        <div style='background-color:#fff3cd; padding:10px; border-radius:6px; margin-bottom:10px;'>
            ✂️ <b>Prochaine tonte estimée :</b><br>
            📆 <i>{format_date(date_prochaine_tonte.date(), format='full', locale='fr')}</i>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='background-color:#d4edda; padding:10px; border-radius:6px; margin-bottom:10px;'>
            🟢 <b>Aucune tonte prévue dans les prochains jours</b>
        </div>
        """, unsafe_allow_html=True)

    # Displaying daily weather forecast
    # Filtrer le DataFrame pour n'afficher que les 8 jours pertinents : aujourd'hui et les 7 prochains jours.
    # Nous utilisons today + pd.Timedelta(days=7) pour inclure 7 jours complets après aujourd'hui.
    df_a_afficher = df[(df["date"] >= today - pd.Timedelta(days=2)) & (df["date"] <= today + pd.Timedelta(days=7))]
    for _, row in df_a_afficher.iterrows(): # <-- Changement ici
        jour = format_date(row["date"].date(), format='dd/MM', locale='fr')
        is_today = (row["date"].date() == today.date())
        card_style = (
            "background-color: #d0f0ff; font-weight: bold;" if is_today else "background-color: #f9f9f9;"
        )
        st.markdown(f"""
        <div style="{card_style} border-radius: 10px; padding: 8px 12px; margin-bottom: 6px;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 0.85em; display: flex; justify-content: space-between; flex-wrap: wrap;">
            <div><b>📅 {jour}</b></div>
            <div>🌡️ {row['temp_max']}°C</div>
            <div>🌧️ {row['pluie']:.1f} mm</div>
            <div>💧 {row['evapo']:.1f}</div>
            <div>☀️ {int(row['radiation']) if pd.notna(row['radiation']) else '-'} W/m²</div>
            <div>🌬️ {int(row['vent']) if pd.notna(row['vent']) else '-'} km/h</div>
        </div>
        """, unsafe_allow_html=True)

    # === 📅 Historique ===
    afficher_calendrier_frise(journal, today) # Make sure this function is defined and handles pd.Timestamps

except Exception as e:
    st.error(f"❌ Erreur générale de l'application : {e}")
