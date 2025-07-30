import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Importation des chemins depuis constants (assurez-vous que constants.PARAM_PATH est défini)
import constants

# Helper function to load JSON files safely
def _load_json_file(filepath, default_data):
    """Helper to load JSON or return default data if file not found or corrupted."""
    if not os.path.exists(filepath):
        st.warning(f"Le fichier {filepath} n'existe pas. Retourne les données par défaut.")
        return default_data
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                st.warning(f"Le fichier {filepath} contient des données mal formées (pas un dictionnaire). Retourne les données par défaut.")
                return default_data
    except json.JSONDecodeError as e:
        st.error(f"Erreur de lecture du fichier JSON {filepath}. Le fichier est peut-être corrompu ou mal formaté. Erreur: {e}")
        return default_data
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue lors du chargement de {filepath} : {e}")
        return default_data


# === Chargement / Sauvegarde des préférences utilisateur ===
def charger_preferences_utilisateur():
    """Charge les préférences utilisateur depuis un fichier JSON local."""
    return _load_json_file(constants.PARAM_PATH, {})

def enregistrer_preferences_utilisateur(prefs: dict):
    """Enregistre les préférences utilisateur dans un fichier JSON."""
    try:
        with open(constants.PARAM_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde des préférences : {e}")

# === Journal des actions (arrosage et tonte) ===
def charger_journal():
    journal_data = _load_json_file(constants.JOURNAL_PATH, {"arrosages": [], "tontes": []})

    # Load user preferences to get current plants for old watering entries
    user_prefs = charger_preferences_utilisateur()
    current_cultivated_plants = user_prefs.get("plantes", [])

    # --- Process 'arrosages' list ---
    processed_arrosages = []
    raw_arrosages = journal_data.get("arrosages", [])

    for i, entry in enumerate(raw_arrosages):
        if isinstance(entry, str): # Handle old format: just a date string
            try:
                processed_arrosages.append({
                    "date": pd.to_datetime(entry),
                    "plants": current_cultivated_plants, # Assign all current plants to old entries
                    "notes": "Ancien enregistrement - toutes plantes arrosées."
                })
            except (ValueError, TypeError) as e:
                st.warning(f"Impossible de convertir l'ancienne date d'arrosage '{entry}' à l'index {i}. Ignorée. Erreur: {e}")
        elif isinstance(entry, dict) and "date" in entry: # Handle new dictionary format
            try:
                date_value_from_json = entry["date"]
                if isinstance(date_value_from_json, str):
                    # If it's a string, convert it to Timestamp
                    entry_date = pd.to_datetime(date_value_from_json)
                elif isinstance(date_value_from_json, pd.Timestamp):
                    # If it's already a Timestamp (e.g., from a previous load and save cycle)
                    entry_date = date_value_from_json
                else:
                    # If the date value is neither a string nor a Timestamp, it's malformed
                    raise ValueError(f"Valeur de date inattendue: {type(date_value_from_json)} - {date_value_from_json}")
                
                entry["date"] = entry_date

                # Ensure 'plants' key exists and is a list
                if "plants" not in entry or not isinstance(entry["plants"], list):
                    entry["plants"] = [] # Default to empty list if missing or wrong type
                
                # Add other optional fields with defaults if they might be missing from older entries
                entry["amount_liters"] = entry.get("amount_liters")
                entry["duration_minutes"] = entry.get("duration_minutes")
                entry["method"] = entry.get("method")
                entry["notes"] = entry.get("notes")

                processed_arrosages.append(entry)
            except (ValueError, TypeError) as e:
                # This warning will now show the actual problematic date value
                st.warning(f"Impossible de convertir la date d'arrosage '{entry.get('date', 'N/A')}' dans l'entrée {i}. Erreur: {e}. Entrée complète: {entry}")
        else:
            st.warning(f"Entrée d'arrosage mal formée ou inattendue à l'index {i} : {entry}. Ignorée.")
    journal_data["arrosages"] = processed_arrosages

    # --- Process 'tontes' list ---
    processed_tontes = []
    for tonte_entry in journal_data.get("tontes", []):
        if isinstance(tonte_entry, dict) and "date" in tonte_entry:
            try:
                # Similar robust check for mowing dates
                date_value_from_json = tonte_entry["date"]
                if isinstance(date_value_from_json, str):
                    tonte_entry["date"] = pd.to_datetime(date_value_from_json)
                elif isinstance(date_value_from_json, pd.Timestamp):
                    tonte_entry["date"] = date_value_from_json
                else:
                    raise ValueError(f"Valeur de date inattendue pour la tonte: {type(date_value_from_json)} - {date_value_from_json}")
                
                processed_tontes.append(tonte_entry)
            except (ValueError, TypeError) as e:
                st.warning(f"Impossible de convertir la date de tonte '{tonte_entry.get('date', 'N/A')}'. Entrée ignorée. Erreur: {e}. Entrée complète: {tonte_entry}")
        else:
            st.warning(f"Entrée de tonte mal formée : {tonte_entry}. Ignorée.")
    journal_data["tontes"] = processed_tontes

    return journal_data

def sauvegarder_journal(journal_data):
    # Create a deep copy to avoid modifying the original dict during serialization
    data_to_save = {
        "arrosages": [],
        "tontes": []
    }
    
    if "arrosages" in journal_data and journal_data["arrosages"]:
        serialized_arrosages = []
        for entry in journal_data["arrosages"]:
            if isinstance(entry, dict) and "date" in entry:
                serialized_entry = {
                    "date": entry["date"].isoformat(), # Convert Timestamp to ISO string for saving
                    "plants": entry.get("plants", []),
                    "amount_liters": entry.get("amount_liters"), 
                    "duration_minutes": entry.get("duration_minutes"),
                    "method": entry.get("method"),
                    "notes": entry.get("notes")
                }
                serialized_entry = {k: v for k, v in serialized_entry.items() if v is not None}
                serialized_arrosages.append(serialized_entry)
            else:
                st.warning(f"Impossible de sérialiser l'entrée d'arrosage : {entry}. Ignorée.")
        data_to_save["arrosages"] = serialized_arrosages
    
    if "tontes" in journal_data and journal_data["tontes"]:
        for tonte in journal_data["tontes"]:
            if isinstance(tonte, dict) and isinstance(tonte.get("date"), pd.Timestamp):
                serialized_tonte = tonte.copy()
                serialized_tonte["date"] = serialized_tonte["date"].isoformat()
                data_to_save["tontes"].append(serialized_tonte)
            else:
                st.warning(f"Impossible de sérialiser l'entrée de tonte : {tonte}. Ignorée.")

    try:
        with open(constants.JOURNAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde du journal : {e}")


@st.cache_data(ttl=86400) # Cache pour 24h, se rafraîchit si le fichier change ou après 24h
def charger_etat_jardin():
    """Charge l'état du déficit hydrique du jardin depuis un fichier JSON."""
    etat = _load_json_file(constants.ETAT_JARDIN_FILE, {
        "date_derniere_maj": None,
        "deficits_accumules": {}
    })
    if etat["date_derniere_maj"]:
        etat["date_derniere_maj"] = pd.to_datetime(etat["date_derniere_maj"])
    return etat

def sauvegarder_etat_jardin(etat):
    """Sauvegarde l'état du déficit hydrique du jardin dans un fichier JSON."""
    # Create a copy to avoid modifying the cached object directly
    etat_to_save = etat.copy() 
    if etat_to_save["date_derniere_maj"]:
        etat_to_save["date_derniere_maj"] = etat_to_save["date_derniere_maj"].strftime('%Y-%m-%d')
    with open(constants.ETAT_JARDIN_FILE, 'w', encoding='utf-8') as f:
        json.dump(etat_to_save, f, indent=2)
    charger_etat_jardin.clear() # Invalider le cache


@st.cache_data(ttl=86400) # Cache for 24 hours, or until file changes
def charger_familles():
    """Charge les données des familles de plantes depuis un fichier JSON (familles_plantes.json)."""
    return _load_json_file(constants.FAMILLES_PLANTES_FILE, {})

# Construction d'un index plante → infos complètes
def construire_index_plantes(familles):
    """Construit un index des plantes associant chaque plante à son nom (string) et toutes ses informations détaillées."""
    index = {}
    for famille_code, infos_famille in familles.items():
        if "plantes" in infos_famille and isinstance(infos_famille["plantes"], list):
            for plante_dict in infos_famille["plantes"]: # 'plante_dict' est le dictionnaire complet de la plante
                if isinstance(plante_dict, dict) and "nom" in plante_dict:
                    plante_nom = plante_dict["nom"]
                    # Stocker le dictionnaire complet de la plante, et ajouter la famille pour référence
                    full_plant_info = plante_dict.copy()
                    full_plant_info["famille"] = famille_code
                    index[plante_nom] = full_plant_info
    return index

@st.cache_data(ttl=86400) # Cache for 24 hours
def charger_recommandations_mensuelles(filepath="recommandations_jardin.json"):
    """
    Charge les recommandations mensuelles depuis un fichier JSON.
    """
    data = _load_json_file(filepath, {})
    return {int(k): v for k, v in data.items()} if data else {}


def get_hauteur_tonte_default(journal_tontes):
    """
    Détermine la hauteur de tonte par défaut pour le slider,
    basée sur la dernière tonte enregistrée ou une valeur fixe.
    """
    hauteur_tonte_input_default = constants.DEFAULT_HAUTEUR_TONTE_INPUT
    if journal_tontes:
        # Filter for valid mowing entries (dictionaries with a 'date' that is a Timestamp)
        valid_tontes = [t for t in journal_tontes if isinstance(t, dict) and "date" in t and isinstance(t["date"], pd.Timestamp)]
        if valid_tontes:
            try:
                # Find the most recent valid mowing entry
                derniere_tonte_info = max(valid_tontes, key=lambda x: x["date"])
                hauteur_tonte_input_default = derniere_tonte_info.get("hauteur", constants.DEFAULT_HAUTEUR_TONTE_INPUT)
            except ValueError: # This can happen if valid_tontes is empty
                pass
    return hauteur_tonte_input_default
