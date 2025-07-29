# ui_components.py
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
    # Convertir les dates du journal en objets date pure pour comparaison
    dates_arrosage = set(d.date() for d in journal.get("arrosages", []) if isinstance(d, (pd.Timestamp, datetime)))
    dates_tonte = set(t["date"].date() for t in journal.get("tontes", []) if isinstance(t, dict) and "date" in t and isinstance(t["date"], (pd.Timestamp, datetime)))

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
        journal (dict): Dictionnaire contenant la liste des arrosages (pd.Timestamp).
    Returns:
        dict: Statistiques calculées.
    """
    arrosages = journal.get("arrosages", [])
    if len(arrosages) < 2:
        return {
            "nb_arrosages": len(arrosages),
            "freq_moyenne_jours": "N/A",
            "dernier_arrosage_date": arrosages[-1].date() if arrosages else None
        }

    # S'assurer que les dates sont triées
    arrosages_sorted = sorted(arrosages)
    
    # Calculer les écarts en jours entre arrosages consécutifs
    ecarts = []
    for i in range(1, len(arrosages_sorted)):
        delta = arrosages_sorted[i] - arrosages_sorted[i-1]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0

    return {
        "nb_arrosages": len(arrosages),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "dernier_arrosage_date": arrosages_sorted[-1].date()
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
    tontes = journal.get("tontes", [])
    if len(tontes) < 2:
        return {
            "nb_tontes": len(tontes),
            "freq_moyenne_jours": "N/A",
            "hauteur_moyenne": tontes[-1]["hauteur"] if tontes else "N/A",
            "derniere_tonte_date": tontes[-1]["date"].date() if tontes else None
        }

    # S'assurer que les tontes sont triées par date
    tontes_sorted = sorted(tontes, key=lambda x: x["date"])
    
    # Calculer les écarts en jours entre tontes consécutives
    ecarts = []
    for i in range(1, len(tontes_sorted)):
        delta = tontes_sorted[i]["date"] - tontes_sorted[i-1]["date"]
        ecarts.append(delta.days)

    freq_moyenne = sum(ecarts) / len(ecarts) if ecarts else 0
    hauteurs = [t["hauteur"] for t in tontes]
    hauteur_moyenne = sum(hauteurs) / len(hauteurs)

    return {
        "nb_tontes": len(tontes),
        "freq_moyenne_jours": round(freq_moyenne, 1),
        "hauteur_moyenne": round(hauteur_moyenne, 1),
        "derniere_tonte_date": tontes_sorted[-1]["date"].date()
    }