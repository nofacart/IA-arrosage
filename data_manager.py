import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Importation des chemins depuis constants
import constants

# === Chargement / Sauvegarde des préférences utilisateur ===
def charger_preferences_utilisateur():
    """Charge les préférences utilisateur depuis un fichier JSON local.

    Retourne un dictionnaire des préférences utilisateur si le fichier existe et est valide,
    sinon un dictionnaire vide.

    Returns:
        dict: Préférences utilisateur.
    """
    if os.path.exists(constants.PARAM_PATH):
        try:
            with open(constants.PARAM_PATH, "r", encoding="utf-8") as f:
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
        with open(constants.PARAM_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde des préférences : {e}")

# === Journal des actions (arrosage et tonte) ===
def charger_journal():
    if os.path.exists(constants.JOURNAL_PATH):
        try:
            with open(constants.JOURNAL_PATH, "r", encoding="utf-8") as f:
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
        with open(constants.JOURNAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"Erreur lors de la sauvegarde du journal : {e}")


@st.cache_data(ttl=86400) # Cache pour 24h, se rafraîchit si le fichier change ou après 24h
def charger_etat_jardin():
    """Charge l'état du déficit hydrique du jardin depuis un fichier JSON."""
    try:
        with open(constants.ETAT_JARDIN_FILE, 'r', encoding='utf-8') as f:
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
    with open(constants.ETAT_JARDIN_FILE, 'w', encoding='utf-8') as f:
        json.dump(etat, f, indent=2)
    # Invalider le cache pour que la prochaine lecture prenne la nouvelle valeur
    charger_etat_jardin.clear()


@st.cache_data(ttl=86400) # Cache for 24 hours, or until file changes
def charger_familles():
    """Charge les données des familles de plantes depuis un fichier JSON (familles_plantes.json)."""
    if not os.path.exists(constants.FAMILLES_PLANTES_FILE):
        st.error(f"Fichier familles_plantes.json introuvable à {constants.FAMILLES_PLANTES_FILE}. Veuillez vous assurer qu'il existe.")
        return {}
    try:
        with open(constants.FAMILLES_PLANTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        st.error(f"Erreur de lecture du fichier familles_plantes.json. Le fichier est peut-être corrompu ou mal formaté. Erreur: {e}")
        return {}
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue lors du chargement des familles de plantes : {e}")
        return {}

# Construction d'un index plante → kc + famille
def construire_index_plantes(familles):
    """Construit un index des plantes associant chaque plante à sa famille et son coefficient kc."""
    index = {}
    for famille, infos in familles.items():
        if "plantes" in infos and isinstance(infos["plantes"], list):
            for plante in infos["plantes"]:
                index[plante] = {
                    "famille": famille,
                    "kc": infos.get("kc", 1.0) # Default kc if not specified
                }
    return index

@st.cache_data(ttl=86400) # Cache for 24 hours
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