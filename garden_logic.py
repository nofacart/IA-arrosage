import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from babel.dates import format_date
import streamlit as st

# Import constants
import constants

# Import data management functions
import data_manager

def calculer_solde_hydrique_accumule(journal_arrosages, familles, plantes_choisies, df_meteo, today, type_sol, paillage):
    """
    Calcule les soldes hydriques accumulés pour chaque instance de plante et de mode de culture.
    Une valeur positive indique un déficit, une valeur négative un surplus.
    
    Args:
        journal_arrosages (list): Liste des événements d'arrosage.
        familles (dict): Dictionnaire des familles de plantes et leurs propriétés.
        plantes_choisies (dict): Dictionnaire où les clés sont les noms de plantes
                                 et les valeurs sont des listes de modes de culture.
                                 Ex: {"tomate": ["bac"], "courgette": ["pleine_terre"]}
        df_meteo (pd.DataFrame): DataFrame des données météorologiques.
        today (pd.Timestamp): Date actuelle.
        type_sol (str): Type de sol sélectionné.
        paillage (bool): Indique si le paillage est présent.

    Returns:
        dict: Soldes hydriques accumulés pour chaque instance de plante.
              Ex: {"tomate_bac": 45.3, "courgette_pleine_terre": -5.2}
    """
    soldes_par_plante_et_mode = {}
    facteur_sol_val = constants.FACTEUR_SOL.get(type_sol, 1.0)
    facteur_paillage_val = constants.FACTEUR_PAILLAGE_REDUCTION if paillage else 1.0
    facteur_bac_val = constants.FACTEUR_BAC

    # Date de début du calcul pour l'historique météo
    start_date_meteo = today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE)

    if not isinstance(df_meteo, pd.DataFrame) or df_meteo.empty:
        print("Erreur: Les données météo ne sont pas au bon format ou sont vides.")
        return {}

    df_periode = df_meteo[(df_meteo["date"] >= start_date_meteo) & (df_meteo["date"] <= today)].copy()
    
    # Créer un mapping de plantes vers leur famille pour une recherche rapide
    plante_to_famille = {p['nom'].lower(): code for code, data in familles.items() for p in data['plantes']}

    # Parcourir chaque instance de plante et son ou ses modes de culture
    for nom_plante, modes_culture in plantes_choisies.items():
        # Déterminer le kc (coefficient cultural) de la plante
        code_famille = plante_to_famille.get(nom_plante.lower(), None)
        if not code_famille:
            continue
        
        kc = familles[code_famille].get("kc", 1.0)
        
        # Parcourir chaque mode de culture associé à cette plante
        for mode_culture in modes_culture:
            # Créer une clé unique pour cette instance
            cle_unique = f"{nom_plante}_{mode_culture}"

            # Définir le facteur d'évapotranspiration en fonction du mode de culture
            facteur_total = 1.0
            if mode_culture == "bac" or mode_culture == "bac_couvert":
                facteur_total = facteur_bac_val
            elif mode_culture == "pleine_terre":
                facteur_total = facteur_sol_val * facteur_paillage_val
            
            s = 0.0 # Initialiser le solde hydrique pour cette instance de plante

            # Préparer le journal des arrosages pour une recherche rapide
            arrosages_par_jour = {}
            for entry in journal_arrosages:
                if isinstance(entry, dict) and "date" in entry:
                    date_str = entry["date"].strftime('%Y-%m-%d')
                    if date_str not in arrosages_par_jour:
                        arrosages_par_jour[date_str] = set()
                    arrosages_par_jour[date_str].update([p.lower() for p in entry.get("plants", [])])

            # Calculer le solde jour après jour
            for _, row in df_periode.iterrows():
                date_str = row["date"].strftime('%Y-%m-%d')
                evapo_jour = row["evapo"]
                pluie_jour = row["pluie"]
                
                besoin_jour = evapo_jour * kc * facteur_total
                s += besoin_jour
                
                # Soustraire la pluie UNIQUEMENT si le mode de culture la reçoit
                if mode_culture in ["pleine_terre", "bac"]:
                    s -= pluie_jour
                
                # Si la plante a été arrosée ce jour-là, le solde est remis à zéro
                if nom_plante.lower() in arrosages_par_jour.get(date_str, set()):
                    s = 0.0
            
            soldes_par_plante_et_mode[cle_unique] = s

    return soldes_par_plante_et_mode

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
