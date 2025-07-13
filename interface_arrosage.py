import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime

# === BASE_DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

# 🌍 CONFIG
DEFAULT_CITY = "Beauzelle"
TIMEZONE = "Europe/Paris"
CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "plantes.json"),
    os.path.join(BASE_DIR, "..", "plantes.json")
]

def charger_plantes():
    for path in CANDIDATE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {
        "tomate": {"kc": 1.15},
        "courgette": {"kc": 1.05},
        "haricot vert": {"kc": 1.0},
        "melon": {"kc": 1.05},
        "fraise": {"kc": 1.05},
        "aromatiques": {"kc": 0.7}
    }

@st.cache_data(ttl=3600)
def recuperer_meteo(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max,et0_fao_evapotranspiration",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": TIMEZONE
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame({
        "date": pd.to_datetime(d["time"]),
        "temp_max": d["temperature_2m_max"],
        "pluie": d["precipitation_sum"],
        "radiation": d.get("shortwave_radiation_sum", [None]*len(d["time"])),
        "vent": d.get("windspeed_10m_max", [None]*len(d["time"])),
        "evapo": d.get("et0_fao_evapotranspiration", [None]*len(d["time"]))
    })

# === APP START ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="centered")
st.title("🌿 Aide à l’arrosage du potager")

try:
    plantes = charger_plantes()
    today = pd.to_datetime(datetime.now().date())

    # --- Paramètres utilisateur ---
    with st.expander("🛠️ Paramètres de votre jardin", expanded=True):
        ville = st.text_input("Ville ou commune :", DEFAULT_CITY)
        infos_ville = get_coords_from_city(ville)

        if infos_ville:
            LAT = infos_ville["lat"]
            LON = infos_ville["lon"]
            st.markdown(f"📍 Ville sélectionnée : **{infos_ville['name']}**, {infos_ville['country']}  \n"
                        f"🌐 Coordonnées : {LAT:.2f}, {LON:.2f}")
        else:
            st.error("❌ Ville non trouvée. Veuillez vérifier l’orthographe.")
            st.stop()

        type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"])
        paillage = st.checkbox("Présence de paillage")
        jours_depuis = st.slider("Jours depuis le dernier arrosage :", 0, 14, 3)

    # Appel dynamique avec coordonnées
    df = recuperer_meteo(LAT, LON)
    df["jour"] = df["date"].dt.strftime("%d/%m")

    facteur_sol = {
        "Sableux": 1.3,
        "Limoneux": 1.0,
        "Argileux": 0.9
    }.get(type_sol, 1.0)
    facteur_paillage = 0.7 if paillage else 1.0

    SEUILS_DEFICIT_SOL = {
        "Sableux": 10,
        "Limoneux": 20,
        "Argileux": 30
    }
    SEUIL_DEFICIT = SEUILS_DEFICIT_SOL.get(type_sol, 20)
    st.caption(f"💧 Seuil de déficit pour arrosage ({type_sol.lower()}) : {SEUIL_DEFICIT} mm")

    # --- Prévision météo courte ---
    df_futur = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=3))]
    jours_chauds_a_venir = (df_futur["temp_max"] >= 30).sum()
    pluie_prochaine_48h = df_futur.head(2)["pluie"].sum()

    if jours_chauds_a_venir >= 2:
        st.warning(f"🔥 {jours_chauds_a_venir} jour(s) ≥30°C à venir. Attention au stress hydrique.")
    if pluie_prochaine_48h >= 10:
        st.info(f"🌧️ {pluie_prochaine_48h:.1f} mm de pluie attendus dans les 48h.")

    # === Calcul recommandations ===
    table_data = []

    for plante, infos in plantes.items():
        kc = infos.get("kc", 1.0)
        nom = plante.capitalize()
        date_depuis = today - pd.Timedelta(days=jours_depuis)

        df_passe = df[(df["date"] >= date_depuis) & (df["date"] <= today)]
        pluie_totale = df_passe["pluie"].sum()
        et0_total = df_passe["evapo"].sum()
        besoin_total = et0_total * kc * facteur_sol * facteur_paillage
        bilan = pluie_totale - besoin_total
        deficit = -bilan if bilan < 0 else 0

        df_prevision = df[(df["date"] > today) & (df["date"] <= today + pd.Timedelta(days=3))]
        pluie_prochaine = df_prevision["pluie"].sum()

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
            "Plante": nom,
            "Recommandation": msg,
            "Couleur": couleur,
            "Détail": infos_bilan
        })

    # --- Résumé du jour ---
    st.markdown("### 🔍 Résumé du jour")
    recommandations = [p for p in table_data if p["Recommandation"] == "Arroser"]
    if recommandations:
        st.error(f"💧 {len(recommandations)} plante(s) à arroser aujourd’hui")
    else:
        st.success("✅ Aucune plante à arroser")

    # --- Affichage recommandations ---
    st.markdown("## 🌱 Recommandations personnalisées")
    for ligne in table_data:
        color = "#F8C17E" if ligne["Couleur"] == "🟧" else "#9EF89E"
        emoji = "💧" if ligne["Recommandation"] == "Arroser" else "✅"
        st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                    f"{emoji} <b>{ligne['Plante']}</b> : {ligne['Recommandation']} – {ligne['Détail']}"
                    f"</div>", unsafe_allow_html=True)

    # --- Météo compact ---
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
