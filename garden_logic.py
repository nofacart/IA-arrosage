import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from babel.dates import format_date
import streamlit as st


# Import constants
import constants

# Import data management functions
import data_manager


# --- Garden Logic Functions ---

def calculer_deficits_accumules(journal_arrosages, familles, plantes_choisies, df_meteo, today, type_sol, paillage):
    """
    Calcule les déficits hydriques accumulés pour les familles de plantes, en tenant compte des arrosages passés.

    Args:
        journal_arrosages (list): Liste des événements d'arrosage.
        familles (dict): Dictionnaire des familles de plantes et leurs propriétés.
        plantes_choisies (list): Liste des noms de plantes sélectionnées par l'utilisateur.
        df_meteo (pd.DataFrame): DataFrame des données météorologiques.
        today (pd.Timestamp): Date actuelle.
        type_sol (str): Type de sol sélectionné.
        paillage (bool): Indique si le paillage est présent.

    Returns:
        dict: Nouveaux déficits accumulés pour chaque famille de plantes.
    """
    nouveaux_deficits_accumules = {}
    facteur_sol_val = constants.FACTEUR_SOL.get(type_sol, 1.0)
    facteur_paillage_val = constants.FACTEUR_PAILLAGE_REDUCTION if paillage else 1.0

    # Date de début du calcul pour l'historique météo
    start_date_meteo = today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE)

    for code_famille, infos_famille in familles.items():
        plantes_famille = [p.get("nom") for p in infos_famille.get("plantes", []) if isinstance(p, dict) and "nom" in p]
        
        # On ne calcule le déficit que pour les familles dont au moins une plante est sélectionnée
        if not any(p_nom in plantes_choisies for p_nom in plantes_famille):
            continue

        kc = infos_famille.get("kc", 1.0)
        
        # Initialiser le déficit pour cette famille
        d = 0.0

        # Parcourir les données météo depuis l'historique disponible jusqu'à aujourd'hui
        # Assurez-vous que df_meteo est bien un DataFrame de Pandas
        if not isinstance(df_meteo, pd.DataFrame):
            st.error("Erreur: Les données météo ne sont pas au bon format.")
            return {}

        df_periode = df_meteo[(df_meteo["date"] >= start_date_meteo) & (df_meteo["date"] <= today)].copy()
        
        # Appliquer les facteurs et calculer le déficit jour après jour
        for index, row in df_periode.iterrows():
            date_jour = row["date"].date()
            evapo_jour = row["evapo"]
            pluie_jour = row["pluie"]
            
            # 1. Ajouter le déficit naturel de la journée
            besoin_jour = evapo_jour * kc * facteur_sol_val * facteur_paillage_val
            d += besoin_jour
            
            # 2. Soustraire la pluie de la journée
            d -= pluie_jour
            
            # 3. Réinitialiser le déficit si un arrosage a eu lieu ce jour-là pour une plante de cette famille
            arrosage_ce_jour = False
            for entry in journal_arrosages:
                if isinstance(entry, dict) and "date" in entry and entry["date"].date() == date_jour:
                    # Vérifier si au moins une plante arrosée appartient à cette famille
                    if any(p in entry.get("plants", []) and p in plantes_famille for p in entry.get("plants", [])):
                        # NOTE: J'ai ajouté une quantité par défaut de 10mm pour un arrosage. Vous pouvez la rendre configurable.
                        d = 0 # Soustraire la quantité d'eau de l'arrosage du déficit
                        arrosage_ce_jour = True
                        break # Un seul arrosage par jour est pris en compte pour une famille

            # 4. S'assurer que le déficit ne devient pas négatif (il ne peut pas y avoir un surplus d'eau dans notre modèle)
            d = max(0.0, d)
        
        # Sauvegarder le déficit final calculé pour la famille
        nouveaux_deficits_accumules[code_famille] = d

    return nouveaux_deficits_accumules

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
