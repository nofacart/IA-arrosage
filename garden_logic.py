import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from babel.dates import format_date

# Import constants
import constants

# Import data management functions
import data_manager


# --- Garden Logic Functions ---

def calculer_deficits_accumules(journal_arrosages, familles, plantes_choisies, df_meteo, today, type_sol, paillage):
    """
    Calcule les déficits hydriques accumulés pour les plantes choisies.
    Cette fonction est appelée chaque jour pour mettre à jour l'état du jardin.
    """
    nouveaux_deficits = {}
    # Use constants for factors
    facteur_sol_val = constants.FACTEUR_SOL.get(type_sol, 1.0)
    facteur_paillage_val = constants.FACTEUR_PAILLAGE_REDUCTION if paillage else 1.0

    # Determine the date of the last global watering to reset deficits
    # This logic needs to be updated to handle the new journal_arrosages format (list of dicts)
    # Filter for valid watering entries (dictionaries with a 'date' that is a Timestamp)
    valid_arrosages = [
        entry for entry in journal_arrosages
        if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], (pd.Timestamp, datetime))
    ]

    if valid_arrosages:
        # Get the date of the latest watering event
        date_dernier_arrosage_global = max(valid_arrosages, key=lambda x: x["date"])["date"]
    else:
        # If no watering is recorded, use an arbitrary date for historical weather data
        date_dernier_arrosage_global = today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE)

    for code_famille, infos_famille in familles.items():
        plantes_famille = infos_famille["plantes"]
        # Only calculate for selected plants that belong to this family
        if not any(p in plantes_choisies for p in plantes_famille):
            continue

        kc = infos_famille["kc"]

        # Filter meteo data from last global watering to today
        df_periode = df_meteo[(df_meteo["date"] > date_dernier_arrosage_global) & (df_meteo["date"] <= today)]

        pluie_delta = df_periode["pluie"].sum()
        et0_delta = df_periode["evapo"].sum()
        besoin_delta = et0_delta * kc * facteur_sol_val * facteur_paillage_val

        # The deficit is how much more water the plant needed than it received
        # If pluie_delta > besoin_delta, there's a surplus, so deficit is 0
        current_deficit = max(0.0, besoin_delta - pluie_delta)

        # If there was an watering today for ANY of the plants in this family, reset deficit for this family
        # This check needs to be updated to handle the new journal_arrosages format
        arrosage_today_for_family = False
        for entry in valid_arrosages:
            if entry["date"].date() == today.date(): # Check if the watering event happened today
                # Check if any plant in this family was part of today's watering event
                if any(p in entry.get("plants", []) for p in plantes_famille):
                    arrosage_today_for_family = True
                    break
        
        if arrosage_today_for_family:
            current_deficit = 0.0

        nouveaux_deficits[code_famille] = current_deficit

    return nouveaux_deficits

def croissance_herbe(temp_max, pluie, evapo):
    """
    Estime la croissance de l'herbe en mm/jour.
    """
    # Explicitly cast to float to prevent any lingering type issues
    temp_max = float(temp_max)
    pluie = float(pluie)
    evapo = float(evapo)

    croissance_base = 0.5

    temp_facteur = 1.0
    if temp_max > 25:
        temp_facteur = 1.0 - (temp_max - 25) * 0.05
    elif temp_max < 10:
        temp_facteur = 0.5

    pluie_facteur = 1.0 + (pluie * 0.1)

    evapo_facteur = 1.0 - (evapo * 0.05)

    temp_facteur = max(0.1, temp_facteur)
    pluie_facteur = max(0.1, pluie_facteur)
    evapo_facteur = max(0.1, evapo_facteur)

    croissance = croissance_base * temp_facteur * pluie_facteur * evapo_facteur
    return max(0, croissance)

def estimer_arrosage_le_plus_contraignant(plantes_choisies, index_plantes, df_futur, seuil_deficit, facteur_sol, facteur_paillage):
    """
    Estime la date du prochain arrosage nécessaire, en se basant sur la plante la plus "contraignante" (celle qui atteint son déficit le plus tôt).
    """
    dates_arrosage_potentielles = []

    for plante in plantes_choisies:
        # Assurez-vous que 'plante' est une clé valide dans index_plantes
        # et que index_plantes.get(plante) retourne un dictionnaire
        infos_plante = index_plantes.get(plante, {})
        kc = infos_plante.get("kc", 1.0) 
        
        cumul_deficit = 0

        for _, row in df_futur.iterrows():
            # Explicitly cast to float to ensure scalar numeric values for calculation
            pluie_jour = float(row["pluie"])
            evapo_jour = float(row["evapo"])

            etc = evapo_jour * kc * facteur_sol * facteur_paillage
            bilan = pluie_jour - etc
            if bilan < 0:
                cumul_deficit += -bilan
            if cumul_deficit >= seuil_deficit:
                dates_arrosage_potentielles.append(row["date"])
                break
    return min(dates_arrosage_potentielles) if dates_arrosage_potentielles else None


def estimer_date_prochaine_tonte(df_futur_meteo, hauteur_actuelle_cm, hauteur_cible_cm):
    """
    Estime la date de la prochaine tonte basée sur la croissance de l'herbe et la hauteur cible.
    """
    if df_futur_meteo.empty:
        return None

    hauteur_estimee = hauteur_actuelle_cm
    seuil_tonte_cm = hauteur_cible_cm * 1.5 # Example: mow when 50% above target

    for _, row in df_futur_meteo.iterrows():
        # Ensure row values are passed as scalars (already done in app.py, but good to be explicit)
        croissance_jour_mm = croissance_herbe(float(row["temp_max"]), float(row["pluie"]), float(row["evapo"]))
        hauteur_estimee += (croissance_jour_mm / 10) # Convert mm to cm

        if hauteur_estimee >= seuil_tonte_cm:
            return row["date"]
    return None
