import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import locale
from babel.dates import format_date
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re

import constants

# Tente de définir la locale pour le formatage des dates
try:
    locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'fra')
    except locale.Error:
        pass # Si aucune locale française n'est trouvée, utilise le comportement par défaut

def afficher_calendrier_frise(journal, today):
    """
    Affiche une frise de 14 jours avec les actions de jardin (arrosage, tonte).
    Args:
        journal (dict): Dictionnaire contenant le journal des actions.
        today (pd.Timestamp): Date d'aujourd'hui.
    """
    jours = [today - pd.Timedelta(days=i) for i in range(13, -1, -1)]
    
    # Extraire les dates des événements d'arrosage
    dates_arrosage = set(
        entry["date"].date() 
        for entry in journal.get("arrosages", []) 
        if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], (pd.Timestamp, datetime))
    )
    
    # Extraire les dates des événements de tonte
    dates_tonte = set(
        t["date"].date() 
        for t in journal.get("tontes", []) 
        if isinstance(t, dict) and "date" in t and isinstance(t["date"], (pd.Timestamp, datetime))
    )

    lignes = []
    for jour in jours:
        jour_nom = jour.strftime("%a %d").capitalize()
        jour_date = jour.date()

        if jour_date in dates_arrosage:
            emoji = "💧"
            action = "Arrosé"
            couleur = "#D4EDDA"
        elif jour_date in dates_tonte:
            emoji = "✂️"
            action = "Tondu"
            couleur = "#D6EAF8"
        else:
            emoji = "—"
            action = "Aucune action"
            couleur = "#F0F0F0"

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

@st.cache_data
def calculer_stats_arrosage(journal):
    """
    Calcule les statistiques d'arrosage.
    Args:
        journal (dict): Dictionnaire contenant la liste des arrosages (maintenant des dictionnaires).
    Returns:
        dict: Statistiques calculées.
    """
    # Filtrer les entrées d'arrosage valides (dictionnaires avec une clé 'date' qui est un Timestamp)
    valid_arrosages = [
        entry for entry in journal.get("arrosages", []) 
        if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], (pd.Timestamp, datetime))
    ]

    if len(valid_arrosages) < 2:
        return {
            "nb_arrosages": len(valid_arrosages),
            "freq_moyenne_jours": "N/A",
            "dernier_arrosage_date": valid_arrosages[-1]["date"].date() if valid_arrosages else None
        }

    # Trier les arrosages par date
    arrosages_sorted_by_date = sorted(valid_arrosages, key=lambda x: x["date"])
    
    # Extraire seulement les objets Timestamp pour le calcul des écarts
    dates_only = [entry["date"] for entry in arrosages_sorted_by_date]

    # Calculer les écarts en jours entre arrosages consécutifs
    ecarts = []
    for i in range(1, len(dates_only)):
        delta = dates_only[i] - dates_only[i-1]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0

    return {
        "nb_arrosages": len(valid_arrosages),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "dernier_arrosage_date": arrosages_sorted_by_date[-1]["date"].date()
    }

@st.cache_data
def calculer_stats_tonte(journal):
    """
    Calcule les statistiques de tonte.
    Args:
        journal (dict): Dictionnaire contenant la liste des tontes.
    Returns:
        dict: Statistiques calculées.
    """
    # Filtrer les entrées de tonte valides (dictionnaires avec une clé 'date' qui est un Timestamp)
    valid_tontes = [
        t for t in journal.get("tontes", []) 
        if isinstance(t, dict) and "date" in t and isinstance(t["date"], (pd.Timestamp, datetime))
    ]

    if len(valid_tontes) < 2:
        return {
            "nb_tontes": len(valid_tontes),
            "freq_moyenne_jours": "N/A",
            "hauteur_moyenne": valid_tontes[-1].get("hauteur", "N/A") if valid_tontes else "N/A",
            "derniere_tonte_date": valid_tontes[-1]["date"].date() if valid_tontes else None
        }

    # S'assurer que les tontes sont triées par date
    tontes_sorted = sorted(valid_tontes, key=lambda x: x["date"])
    
    # Extraire les dates des tontes pour le calcul des écarts
    dates_only = [t["date"] for t in tontes_sorted]

    # Calculer les écarts en jours entre tontes consécutives
    ecarts = []
    for i in range(1, len(dates_only)):
        delta = dates_only[i] - dates_only[i-1]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0
    
    # Extraire les hauteurs pour le calcul de la moyenne
    hauteurs = [t.get("hauteur") for t in valid_tontes if t.get("hauteur") is not None]
    hauteur_moyenne = sum(hauteurs) / len(hauteurs) if hauteurs else "N/A"

    return {
        "nb_tontes": len(valid_tontes),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "hauteur_moyenne": round(hauteur_moyenne, 1) if isinstance(hauteur_moyenne, (int, float)) else hauteur_moyenne,
        "derniere_tonte_date": tontes_sorted[-1]["date"].date()
    }

def get_months_from_period_string(period_str):
    """
    Parses a period string (e.g., "Mars-Avril (intérieur), Mai (extérieur)")
    and returns a sorted list of month numbers (1-12) implied.
    """
    months_map = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    
    found_months = set()
    period_str_lower = period_str.lower()

    # Look for single month names
    for month_name, month_num in months_map.items():
        if re.search(r'\b' + re.escape(month_name) + r'\b', period_str_lower):
            found_months.add(month_num)
    
    # Look for ranges like "Mars-Avril" or "mars-avril"
    for m1_name, m1_num in months_map.items():
        for m2_name, m2_num in months_map.items():
            if f"{m1_name}-{m2_name}" in period_str_lower:
                if m1_num <= m2_num:
                    for m in range(m1_num, m2_num + 1):
                        found_months.add(m)
                else: # Crosses year boundary
                    for m in range(m1_num, 13):
                        found_months.add(m)
                    for m in range(1, m2_num + 1):
                        found_months.add(m)
    
    return sorted(list(found_months))

# --- Fonctions utilitaires pour l'affichage des fiches plantes ---
def generate_planting_frieze(periode_semis_str):
    """
    Génère une frise visuelle des mois de plantation.
    🟩 = mois de plantation, ⬜ = mois sans plantation.
    """
    all_months = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    frieze_emojis = []
    
    # Mappe les noms de mois courants/abréviations à leur index (0-11)
    month_map = {
        "jan": 0, "fév": 1, "mar": 2, "avr": 3, "mai": 4, "juin": 5,
        "juil": 6, "août": 7, "sep": 8, "oct": 9, "nov": 10, "déc": 11,
        "janvier": 0, "février": 1, "mars": 2, "avril": 3, "juillet": 6,
        "aout": 7, "septembre": 8, "octobre": 9, "novembre": 10, "décembre": 11
    }
    
    # Identifie les mois actifs
    active_months_indices = set()
    # Nettoie la chaîne pour faciliter la correspondance
    parts = periode_semis_str.lower().replace(",", " ").replace("(", " ").replace(")", " ").split()

    for part in parts:
        # Gère les noms de mois directs
        if part in month_map:
            active_months_indices.add(month_map[part])
        # Gère les plages comme "mars-avril"
        elif '-' in part:
            start_month_str, end_month_str = part.split('-')
            if start_month_str in month_map and end_month_str in month_map:
                start_idx = month_map[start_month_str]
                end_idx = month_map[end_month_str]
                # Gère les boucles autour de la fin de l'année (ex: Nov-Fév)
                if start_idx <= end_idx:
                    for i in range(start_idx, end_idx + 1):
                        active_months_indices.add(i)
                else: # Boucle autour de l'année
                    for i in range(start_idx, 12):
                        active_months_indices.add(i)
                    for i in range(0, end_idx + 1):
                        active_months_indices.add(i)

    # La fonction retourne les emojis et les initiales séparément
    return [
        "🟩" if i in active_months_indices else "⬜" for i in range(12)
    ], [
        m[0] for m in all_months
    ]

def get_sunlight_icon(besoins_lumiere_str):
    """Retourne une icône et le texte pour les besoins en lumière."""
    if "plein soleil" in besoins_lumiere_str.lower():
        return "☀️ Plein soleil"
    elif "mi-ombre" in besoins_lumiere_str.lower():
        return "🌤️ Mi-ombre"
    elif "ombre" in besoins_lumiere_str.lower():
        return "☁️ Ombre"
    else:
        return besoins_lumiere_str # Retourne le texte original si pas de correspondance