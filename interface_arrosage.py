import streamlit as st
import requests
import pandas as pd
import json
import os
import math
from datetime import datetime

# === BASE_DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# === Fichier de paramètres utilisateur ===
PARAM_PATH = os.path.join(BASE_DIR, "parametres_utilisateur.json")

def charger_preferences_utilisateur():
    if os.path.exists(PARAM_PATH):
        try:
            with open(PARAM_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("plantes", [])
        except Exception:
            return []
    return []

def enregistrer_preferences_utilisateur(plantes_choisies):
    with open(PARAM_PATH, "w", encoding="utf-8") as f:
        json.dump({"plantes": plantes_choisies}, f, ensure_ascii=False, indent=2)

@st.cache_data(ttl=3600)
def get_coords_from_city(city_name):
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
            "country": first.get("country", ""),
        }
    return None

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

# 🌱 Chargement des plantes
CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json")
]

def charger_familles():
    path = os.path.join(BASE_DIR, "familles_plantes.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def construire_index_plantes(familles):
    index = {}
    for famille, infos in familles.items():
        for plante in infos["plantes"]:
            index[plante] = {
                "famille": famille,
                "kc": infos["kc"]
            }
    return index


# 📊 Récupération des données météo
@st.cache_data(ttl=3600)
def recuperer_meteo(lat, lon):
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
    rad = d.get("shortwave_radiation_sum", [None]*len(temp))
    vent_kmh = d.get("windspeed_10m_max", [None]*len(temp))
    evapo = d.get("et0_fao_evapotranspiration")

    # Calcul de l'évapotranspiration si absente
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

# === APP START ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="centered")
st.title("🌿 Aide au jardinage")

try:
    today = pd.to_datetime(datetime.now().date())

    familles = charger_familles()
    plantes_index = construire_index_plantes(familles)


    JOURNAL_PATH = os.path.join(BASE_DIR, "journal_jardin.json")

    def charger_journal():
        if os.path.exists(JOURNAL_PATH):
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"arrosages": [], "tontes": []}

    def sauvegarder_journal(data):
        with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    journal = charger_journal()

    with st.expander("📆 Suivi journalier", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ J’ai arrosé aujourd’hui"):
                journal["arrosages"].append(str(today.date()))
                sauvegarder_journal(journal)
                st.success("💧 Arrosage enregistré.")
        with col2:
            if st.button("✂️ J’ai tondu aujourd’hui"):
                journal["tontes"].append(str(today.date()))
                sauvegarder_journal(journal)
                st.success("✂️ Tonte enregistrée.")

        if journal["arrosages"]:
            st.markdown(f"**Dernier arrosage enregistré :** {journal['arrosages'][-1]}")
        if journal["tontes"]:
            st.markdown(f"**Dernière tonte enregistrée :** {journal['tontes'][-1]}")

    with st.expander("🌱 Mon potager", expanded=False):
        toutes_les_plantes = sorted(plantes_index.keys())
        plantes_par_defaut = charger_preferences_utilisateur()
        plantes_choisies = st.multiselect(
            "Sélectionnez les plantes cultivées :",
            toutes_les_plantes,
            default=plantes_par_defaut
        )
        enregistrer_preferences_utilisateur(plantes_choisies)
        if st.button("🔁 Réinitialiser la sélection de plantes"):
            enregistrer_preferences_utilisateur([])
            st.experimental_rerun()

    with st.expander("🛠️ Paramètres de votre jardin", expanded=False):
        ville = st.text_input("Ville ou commune :", "Beauzelle")
        infos_ville = get_coords_from_city(ville)

        if infos_ville:
            LAT = infos_ville["lat"]
            LON = infos_ville["lon"]
            st.markdown(f"📍 Ville sélectionnée : **{infos_ville['name']}**, {infos_ville['country']}  \n"
                        f"🌐 Coordonnées : {LAT:.2f}, {LON:.2f}")
        else:
            st.error("❌ Ville non trouvée.")
            st.stop()

        type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"])
        paillage = st.checkbox("Présence de paillage")
    
    with st.expander("💧 Arrosage", expanded=False):
        if journal["arrosages"]:
            date_dernier_arrosage = pd.to_datetime(journal["arrosages"][-1])
            jours_depuis = (today - date_dernier_arrosage).days
            st.markdown(f"💧 Dernier arrosage enregistré : il y a **{jours_depuis} jour(s)**")
        else:
            jours_depuis = st.slider("Jours depuis le dernier arrosage :", 0, 14, 3)

    df = recuperer_meteo(LAT, LON)
    df["jour"] = df["date"].dt.strftime("%d/%m")

    # === Bloc tonte de pelouse ===
    with st.expander("✂️ Tonte de la pelouse", expanded=False):
        if journal["tontes"]:
            date_dernier_tonte = pd.to_datetime(journal["tontes"][-1])
            jours_depuis_tonte = (today - date_dernier_tonte).days
            st.markdown(f"✂️ Dernière tonte enregistrée : il y a **{jours_depuis_tonte} jour(s)**")
        else:
            jours_depuis_tonte = st.slider("Jours depuis la dernière tonte :", 1, 21, 7)
            date_dernier_tonte = today - pd.Timedelta(days=jours_depuis_tonte)

        hauteur_cible_cm = st.slider("Hauteur cible de pelouse (cm) :", 3, 8, 5)

        date_dernier_tonte = today - pd.Timedelta(days=jours_depuis_tonte)
        df_tonte = df[(df["date"] >= date_dernier_tonte) & (df["date"] <= today)].copy()

    # Fonction estimation croissance mm/j selon température + pluie
    def croissance_herbe(temp_moy, pluie):
        if temp_moy < 10:
            return 1
        elif 10 <= temp_moy < 15:
            return 2
        elif 15 <= temp_moy < 25:
            return 6 if pluie >= 2 else 4
        elif temp_moy >= 25:
            return 2 if pluie >= 5 else 1
        return 3

    df_tonte["croissance"] = df_tonte.apply(
        lambda row: croissance_herbe(row["temp_max"], row["pluie"]),
        axis=1
    )
    croissance_totale_mm = df_tonte["croissance"].sum()
    hauteur_estimee_cm = croissance_totale_mm / 10  # 10 mm = 1 cm

    st.markdown(f"📏 Hauteur estimée actuelle : **{hauteur_estimee_cm:.1f} cm**")

    facteur_sol = {"Sableux": 1.3, "Limoneux": 1.0, "Argileux": 0.9}.get(type_sol, 1.0)
    facteur_paillage = 0.7 if paillage else 1.0

    SEUILS_DEFICIT_SOL = {"Sableux": 10, "Limoneux": 20, "Argileux": 30}
    SEUIL_DEFICIT = SEUILS_DEFICIT_SOL.get(type_sol, 20)
    st.caption(f"💧 Seuil de déficit pour arrosage ({type_sol.lower()}) : {SEUIL_DEFICIT} mm")

    df_futur = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=3))]
    jours_chauds_a_venir = (df_futur["temp_max"] >= 30).sum()
    pluie_prochaine_48h = df_futur.head(2)["pluie"].sum()

    
    # === Calcul des recommandations d’arrosage par famille cultivée ===
    table_data = []

    for code_famille, infos_famille in familles.items():
        plantes_de_cette_famille = infos_famille["plantes"]
        if not any(p in plantes_choisies for p in plantes_de_cette_famille):
            continue  # Aucune plante de cette famille n'est cultivée

        kc = infos_famille["kc"]
        # Liste des plantes de cette famille sélectionnées par l’utilisateur
        plantes_cultivees_famille = [p.capitalize() for p in plantes_de_cette_famille if p in plantes_choisies]

        # Nom d'affichage = liste des plantes
        nom_affiche = ", ".join(plantes_cultivees_famille)


        date_depuis = today - pd.Timedelta(days=jours_depuis)
        df_passe = df[(df["date"] >= date_depuis) & (df["date"] <= today)]
        pluie_totale = df_passe["pluie"].sum()
        et0_total = df_passe["evapo"].sum()

        besoin_total = et0_total * kc * facteur_sol * facteur_paillage
        bilan = pluie_totale - besoin_total
        deficit = max(-bilan, 0)

        pluie_prochaine = df_futur["pluie"].sum()

        if deficit == 0:
            besoin = False
            infos_bilan = f"✅ Excédent : {bilan:.1f} mm"
        elif deficit <= SEUIL_DEFICIT:
            besoin = False
            infos_bilan = f"🤏 Déficit léger : {deficit:.1f} mm"
        else:
            if pluie_prochaine >= deficit:
                besoin = False
                infos_bilan = f"🌧️ Pluie prévue ({pluie_prochaine:.1f} mm) compensera"
            else:
                besoin = True
                infos_bilan = f"💧 Déficit : {deficit:.1f} mm"

        couleur = "🟧" if besoin else "🟦"
        msg = "Arroser" if besoin else "Pas besoin"

        table_data.append({
            "Plante": nom_affiche,
            "Recommandation": msg,
            "Couleur": couleur,
            "Détail": infos_bilan
        })


    st.markdown("### 🔍 Résumé du jour")
    if jours_chauds_a_venir >= 2:
        st.warning(f"🔥 {jours_chauds_a_venir} jour(s) ≥30°C à venir.")
    if pluie_prochaine_48h >= 10:
        st.info(f"🌧️ {pluie_prochaine_48h:.1f} mm de pluie attendus dans les 48h.")

    if hauteur_estimee_cm > 1.5 * hauteur_cible_cm:
        st.warning("✂️ Tonte recommandée : l’herbe a trop poussé")
    elif hauteur_estimee_cm > hauteur_cible_cm:
        st.info("🔍 Surveillez : la tonte pourrait bientôt être utile")
    else:
        st.success("✅ Pas besoin de tondre actuellement")

    recommandations = [p for p in table_data if p["Recommandation"] == "Arroser"]
    if recommandations:
        st.error(f"💧 {len(recommandations)} plante(s) à arroser aujourd’hui")
    else:
        st.success("✅ Aucune plante à arroser")

    st.markdown("## 🌱 Recommandations personnalisées")
    for ligne in table_data:
        color = "#F8C17E" if ligne["Couleur"] == "🟧" else "#9EF89E"
        emoji = "💧" if ligne["Recommandation"] == "Arroser" else "✅"
        st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                    f"{emoji} <b>{ligne['Plante']}</b> : {ligne['Recommandation']} – {ligne['Détail']}"
                    f"</div>", unsafe_allow_html=True)

    st.markdown("### 📅 Météo des 14 jours")
    for _, row in df.iterrows():
        jour = row["jour"]
        is_today = (jour == today.strftime("%d/%m"))
        card_style = (
            "background-color: #d0f0ff; font-weight: bold;" if is_today else "background-color: #f9f9f9;"
        )
        st.markdown(f"""
        <div style="
            {card_style}
            border-radius: 10px;
            padding: 8px 12px;
            margin-bottom: 6px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 0.85em;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
        ">
            <div><b>📅 {jour}</b></div>
            <div>🌡️ {row['temp_max']}°C</div>
            <div>🌧️ {row['pluie']:.1f} mm</div>
            <div>💧 {row['evapo']:.1f}</div>
            <div>☀️ {int(row['radiation']) if row['radiation'] else '-'} W/m²</div>
            <div>🌬️ {int(row['vent']) if row['vent'] else '-'} km/h</div>
        </div>
        """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ Erreur : {e}")
