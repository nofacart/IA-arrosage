import pandas as pd
import requests
import math
from datetime import datetime
import streamlit as st # Pour st.cache_data, st.error, etc.
import json # Explicitly import json for json.JSONDecodeError

# === Météo : géocodage d'une ville vers latitude/longitude ===
@st.cache_data(ttl=86400) # Cache pour 24h
def get_coords_from_city(city_name):
    """Récupère les coordonnées géographiques (latitude, longitude) d'une ville donnée."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city_name, "count": 1, "language": "fr", "format": "json"}
    try:
        r = requests.get(url, params=params)
        r.raise_for_status() # Lève une exception pour les codes d'état d'erreur
        results = r.json().get("results")
        if results:
            first = results[0]
            return {
                "lat": first["latitude"],
                "lon": first["longitude"],
                "name": first["name"],
                "country": first.get("country", "")
            }
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur de connexion à l'API de géocodage : {e}")
    except json.JSONDecodeError: # Correctly imported json
        st.error("Erreur de décodage JSON de la réponse de l'API de géocodage.")
    return None

# === Calcul FAO ET₀ simplifié ===
def calcul_evapotranspiration_fao(temp, rad, vent, altitude=150):
    """Calcule l'évapotranspiration de référence (ET₀) selon la méthode FAO simplifiée.
    :param temp: Température moyenne journalière en °C.
    :param rad: Radiation solaire à ondes courtes en MJ/m²/jour.
    :param vent: Vitesse moyenne du vent à 2m en m/s.
    :param altitude: Altitude du lieu en mètres.
    :return: ET₀ en mm/jour.
    """
    albedo = 0.23
    G = 0    # Flux de chaleur au sol, souvent négligé pour les calculs journaliers
    
    # Convertir radiation de MJ/m²/jour en équivalent évaporation (mm)
    # 1 MJ/m²/jour = 0.408 mm/jour (pour l'évaporation de l'eau pure)
    # R_n (Net radiation) = (1 - albedo) * Incoming Shortwave Radiation
    R_n = (1 - albedo) * rad * 0.408 # Convert MJ/m²/jour to mm/jour equivalent (latent heat of vaporization)

    # Pression atmosphérique
    P = 101.3 * ((293 - 0.0065 * altitude) / 293)**5.26 # kPa

    # Pente de la courbe de pression de vapeur saturante (delta)
    # Equation du livre FAO 56, page 36, Eq 3-4
    delta = 4098 * (0.6108 * math.exp((17.27 * temp)/(temp + 237.3))) / ((temp + 237.3)**2) # kPa/°C

    # Constante psychrométrique (gamma)
    # Equation du livre FAO 56, page 37, Eq 3-6
    gamma = 0.665e-3 * P # kPa/°C

    # Pression de vapeur saturante à la température de l'air (e_s)
    # Equation du livre FAO 56, page 36, Eq 3-1 et 3-2 (moyenne de Tmax et Tmin si disponibles, sinon Tavg)
    e_s = 0.6108 * math.exp((17.27 * temp)/(temp + 237.3)) # kPa (ici, basé sur la seule température disponible)

    # Pression de vapeur réelle (e_a)
    # Cette valeur nécessite l'humidité relative. Si l'on n'a pas l'humidité, on peut faire des approximations.
    # L'approximation "50% d'humidité relative" est une simplification très grossière.
    # Pour une approximation plus robuste sans HR, on pourrait utiliser la température minimale comme proxy du point de rosée
    # ou simplement omettre ce terme pour une version encore plus simplifiée si c'est pour une ET₀ "potentielle" max.
    # Étant donné que Open-Meteo fournit l'ET0 directement, cette fonction est surtout un fallback.
    e_a = e_s * 0.75 # kPa (approximation: assuming 75% relative humidity for a typical day, adjust as needed)
                     # Using 0.5 can lead to very high ET0 values if the air is assumed very dry.
                     # A higher relative humidity (e.g., 60-80%) might be more realistic for many climates.
    
    # Vitesse du vent à 2m (u2) - L'API donne déjà 10m, donc c'est direct
    u2 = vent # m/s

    # Formule de Penman-Monteith (simplifiée/approximée comme dans certaines implémentations)
    # Les coefficients 900 et 0.34 sont spécifiques à l'équation pour ET0
    # C'est une combinaison de termes radiatifs et aérodynamiques.
    numerator = 0.408 * delta * (R_n - G) + gamma * (900 / (temp + 273)) * u2 * (e_s - e_a)
    denominator = delta + gamma * (1 + 0.34 * u2)
    
    ET0 = numerator / denominator
    
    return round(max(ET0, 0), 2) # ET0 cannot be negative

# === Données météo quotidiennes ===
@st.cache_data(ttl=3600) # Cache pour 1 heure (les prévisions changent plus souvent que les coords)
def recuperer_meteo(lat, lon):
    """Récupère les données météo journalières pour une latitude et longitude données."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max,et0_fao_evapotranspiration",
        "past_days": 7, # Retrieve 7 past days
        "forecast_days": 14, # Retrieve 14 forecast days for better long-term estimation
        "timezone": "Europe/Paris"
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        d = r.json()["daily"]

        temp = d["temperature_2m_max"]
        pluie = d["precipitation_sum"]
        rad = d.get("shortwave_radiation_sum", [0] * len(temp))
        vent_kmh = d.get("windspeed_10m_max", [0] * len(temp))
        evapo_api = d.get("et0_fao_evapotranspiration") # Renamed to avoid conflict

        # Prepare a list for final ET0 values
        final_evapo = []

        # Iterate through data to decide between API ET0 and calculated ET0
        for i in range(len(d["time"])):
            t_day = temp[i]
            r_day = rad[i]
            v_day_kmh = vent_kmh[i]
            v_day_ms = v_day_kmh / 3.6 # Convert km/h to m/s for calculation

            # Check if API's ET0 is valid for this day, otherwise calculate
            if evapo_api and evapo_api[i] is not None and not math.isnan(evapo_api[i]):
                final_evapo.append(evapo_api[i])
            else:
                # Need to handle cases where inputs to calcul_evapotranspiration_fao might be None or 0
                if None in (t_day, r_day, v_day_ms) or t_day == 0 or r_day == 0:
                    # Provide a default or log a warning if inputs are bad
                    final_evapo.append(0.0) # Default to 0 if input data is insufficient
                else:
                    try:
                        calculated_et0 = calcul_evapotranspiration_fao(t_day, r_day, v_day_ms)
                        final_evapo.append(calculated_et0)
                    except Exception as calc_e:
                        st.warning(f"Erreur lors du calcul de l'ET0 pour la date {d['time'][i]}: {calc_e}. Valeur par défaut de 0 utilisée.")
                        final_evapo.append(0.0) # Fallback if calculation fails

        return pd.DataFrame({
            "date": pd.to_datetime(d["time"]),
            "temp_max": temp,
            "pluie": pluie,
            "radiation": rad,
            "vent": vent_kmh, # Keep in km/h for display if needed
            "evapo": final_evapo # This now holds either API value or calculated fallback
        })
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur de connexion à l'API Météo : {e}")
        return pd.DataFrame() # Retourne un DataFrame vide en cas d'erreur
    except json.JSONDecodeError:
        st.error("Erreur de décodage JSON de la réponse de l'API Météo.")
        return pd.DataFrame()
    except KeyError as e:
        st.error(f"Donnée manquante dans la réponse de l'API Météo : {e}. Vérifiez les paramètres 'daily'.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue lors de la récupération des données météo : {e}")
        return pd.DataFrame()