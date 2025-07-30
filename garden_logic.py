import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from babel.dates import format_date

# Import constants
import constants

# Import data management functions
import data_manager


# --- Garden Logic Functions ---

def calculer_deficits_accumules(journal_arrosages, familles, plantes_choisies, df_meteo, today, type_sol, paillage,
                                 deficits_precedents, date_derniere_maj_precedente):
    """
    Calcule les déficits hydriques accumulés pour les plantes choisies, en reprenant l'état précédent.
    Cette fonction est appelée chaque jour pour mettre à jour l'état du jardin.
    
    Args:
        journal_arrosages (list): Liste des événements d'arrosage.
        familles (dict): Dictionnaire des familles de plantes et leurs propriétés.
        plantes_choisies (list): Liste des noms de plantes sélectionnées par l'utilisateur.
        df_meteo (pd.DataFrame): DataFrame des données météorologiques (historique et prévisions).
        today (pd.Timestamp): Date actuelle.
        type_sol (str): Type de sol sélectionné.
        paillage (bool): Indique si le paillage est présent.
        deficits_precedents (dict): Déficits accumulés lors de la dernière mise à jour.
        date_derniere_maj_precedente (pd.Timestamp): Date de la dernière mise à jour des déficits.
        
    Returns:
        dict: Nouveaux déficits accumulés pour chaque famille de plantes.
    """
    # Commencer avec les déficits de la veille pour les accumuler
    nouveaux_deficits_accumules = deficits_precedents.copy()

    facteur_sol_val = constants.FACTEUR_SOL.get(type_sol, 1.0)
    facteur_paillage_val = constants.FACTEUR_PAILLAGE_REDUCTION if paillage else 1.0

    # Déterminer la date de début pour le calcul des nouveaux déficits
    # C'est le jour après la dernière mise à jour de l'état du jardin
    if date_derniere_maj_precedente is None:
        # Si aucune mise à jour précédente, calculer depuis le début de l'historique météo disponible
        start_date_for_new_calc = today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE)
    else:
        # Calculer à partir du jour suivant la dernière mise à jour
        start_date_for_new_calc = date_derniere_maj_precedente + pd.Timedelta(days=1)

    # Filtrer les événements d'arrosage qui ont eu lieu AUJOURD'HUI pour la logique de réinitialisation
    valid_arrosages_today = [
        entry for entry in journal_arrosages
        if isinstance(entry, dict) and "date" in entry and entry["date"].date() == today.date()
    ]

    for code_famille, infos_famille in familles.items():
        plantes_famille = [p.get("nom") for p in infos_famille.get("plantes", []) if isinstance(p, dict) and "nom" in p]
        
        # Ne calculer que pour les familles dont au moins une plante est sélectionnée par l'utilisateur
        if not any(p_nom in plantes_choisies for p_nom in plantes_famille):
            # Si la famille n'est plus sélectionnée, la retirer des déficits accumulés si elle y est
            if code_famille in nouveaux_deficits_accumules:
                del nouveaux_deficits_accumules[code_famille]
            continue # Passer à la famille suivante

        kc = infos_famille.get("kc", 1.0)

        # Filtrer les données météo pour la période depuis la dernière mise à jour jusqu'à aujourd'hui
        df_periode_new_calc = df_meteo[(df_meteo["date"] >= start_date_for_new_calc) & (df_meteo["date"] <= today)]

        pluie_periode = df_periode_new_calc["pluie"].sum()
        evapo_periode = df_periode_new_calc["evapo"].sum()
        besoin_periode = evapo_periode * kc * facteur_sol_val * facteur_paillage_val

        # Récupérer le déficit accumulé précédent pour cette famille, ou 0.0 si non existant
        current_accumulated_deficit = nouveaux_deficits_accumules.get(code_famille, 0.0)
        
        # Calculer le changement de déficit pour cette période (besoin - pluie)
        deficit_change = besoin_periode - pluie_periode
        
        # Ajouter ce changement au déficit accumulé
        current_accumulated_deficit += deficit_change
        
        # S'assurer que le déficit ne devient pas négatif (un surplus ne s'accumule pas négativement)
        current_accumulated_deficit = max(0.0, current_accumulated_deficit)

        # Vérifier si un arrosage a eu lieu AUJOURD'HUI pour cette famille spécifique
        arrosage_today_for_this_family = False
        for entry in valid_arrosages_today:
            # Vérifier si l'une des plantes arrosées aujourd'hui appartient à cette famille
            if any(p in entry.get("plants", []) and p in plantes_famille for p in entry.get("plants", [])):
                arrosage_today_for_this_family = True
                break
        
        if arrosage_today_for_this_family:
            current_accumulated_deficit = 0.0 # Réinitialiser le déficit pour cette famille si arrosée aujourd'hui

        nouveaux_deficits_accumules[code_famille] = current_accumulated_deficit
    
    # S'assurer que seuls les déficits des plantes choisies sont conservés
    final_deficits = {}
    for plante_nom in plantes_choisies:
        # Trouver la famille de la plante
        famille_trouvee = None
        for famille_code, infos_famille in familles.items():
            if any(p.get("nom") == plante_nom for p in infos_famille.get("plantes", []) if isinstance(p, dict)):
                famille_trouvee = famille_code
                break
        if famille_trouvee:
            final_deficits[famille_trouvee] = nouveaux_deficits_accumules.get(famille_trouvee, 0.0)

    return final_deficits

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
