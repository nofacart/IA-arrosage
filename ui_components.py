import streamlit as st
import pandas as pd
from datetime import datetime
import locale
from babel.dates import format_date
import matplotlib.pyplot as plt # Pour afficher_evolution_pelouse
import matplotlib.dates as mdates # Pour formater les dates sur les graphiques

import constants # Pour les constantes par défaut si besoin

# Tente de définir la locale pour le formatage des dates
try:
    locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'fra')
    except locale.Error:
        pass # Si aucune locale française n'est trouvée, utilise le comportement par défaut

def afficher_calendrier_frise(journal, today):
    """Affiche une frise de 14 jours avec les actions de jardin (arrosage, tonte)."""
    jours = [today - pd.Timedelta(days=i) for i in range(13, -1, -1)]
    
    # Extraire les dates des événements d'arrosage (qui sont maintenant des dictionnaires)
    # Filtrer pour s'assurer que l'entrée est un dictionnaire et contient une clé 'date' qui est un Timestamp
    dates_arrosage = set(
        entry["date"].date() 
        for entry in journal.get("arrosages", []) 
        if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], (pd.Timestamp, datetime))
    )
    
    # Extraire les dates des événements de tonte (déjà des dictionnaires)
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
            emoji = "✅"
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

