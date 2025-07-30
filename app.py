import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
from babel.dates import format_date

# Import constants
import constants

# Import functions from your garden_logic.py
import garden_logic

# Import data management functions
import data_manager 

# Import UI component functions from ui_components.py
import ui_components

# Import weather utilities
from weather_utils import get_coords_from_city, recuperer_meteo

# === 🌿 CONFIGURATION GÉNÉRALE DE LA PAGE ===
st.set_page_config(page_title="🌿 Arrosage potager", layout="centered")
st.title("🌿 Aide au jardinage")

try:
    today = pd.to_datetime(datetime.now().date())
    current_month = str(today.month) # Convertir le mois en chaîne pour correspondre aux clés JSON

    recommendations_mensuelles = data_manager.charger_recommandations_mensuelles()

    # 🔧 Chargement des préférences utilisateur (plantes, paillage, sol)
    prefs = data_manager.charger_preferences_utilisateur()
    plantes_par_defaut = prefs.get("plantes", [])
    paillage_defaut = prefs.get("paillage", False)
    type_sol_defaut = prefs.get("type_sol", "Limoneux")

    # 📚 Chargement des familles de plantes et index
    familles = data_manager.charger_familles()
    plantes_index = data_manager.construire_index_plantes(familles)

    # 📖 Chargement du journal des actions (arrosage et tonte)
    journal = data_manager.charger_journal()

    # 💧 Chargement de l'état du jardin (déficits hydriques)
    etat_jardin = data_manager.charger_etat_jardin()

    # Définir la date de départ pour le calcul du delta météo
    # La logique doit maintenant gérer le nouveau format de journal["arrosages"] (liste de dictionnaires)
    # Filtrer les entrées d'arrosage valides pour s'assurer que 'max' ne s'applique qu'aux dictionnaires
    valid_arrosages_for_delta = [
        entry for entry in journal["arrosages"]
        if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], pd.Timestamp)
    ]

    if valid_arrosages_for_delta:
        # Trouver la date du dernier arrosage à partir du nouveau format de dictionnaire
        latest_watering_event_for_delta = max(valid_arrosages_for_delta, key=lambda x: x["date"])
        latest_watering_date_journal = latest_watering_event_for_delta["date"]
    else:
        # Si aucun arrosage n'est enregistré, utiliser une date par défaut
        latest_watering_date_journal = today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE)

    if etat_jardin["date_derniere_maj"] is None or etat_jardin["date_derniere_maj"] < today - pd.Timedelta(days=constants.METEO_HISTORIQUE_DISPONIBLE):
        date_depart_delta_meteo = latest_watering_date_journal
    else:
        date_depart_delta_meteo = etat_jardin["date_derniere_maj"]

    # Obtenez la hauteur de tonte par défaut
    hauteur_tonte_input_default = data_manager.get_hauteur_tonte_default(journal["tontes"])

    # Tabs for navigation
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📆 Suivi journalier",
        "💧 Synthèse de mon jardin",
        "📈 Suivi Météo",
        "📊 Mon Jardin en chiffre",
        "🌱 Mon Potager & Paramètres"
    ])

    with tab1:
        st.header("📆 Suivi du Jour")

        st.markdown("### Actions Rapides")

        col_arrosage, col_tonte = st.columns(2)

        with col_arrosage:
            # Utiliser un formulaire Streamlit pour une meilleure gestion des widgets
            with st.form("arrosage_form"):
                st.subheader("💧 Enregistrer un Arrosage")
                
                # 'plantes_par_defaut' est déjà chargé depuis 'parametres_utilisateur.json'
                available_plants_for_selection = plantes_par_defaut

                # Permettre à l'utilisateur de sélectionner plusieurs plantes, par défaut toutes les plantes cultivées
                selected_plants_for_watering = st.multiselect(
                    "Quelles plantes ou zones avez-vous arrosées ?",
                    options=available_plants_for_selection,
                    default=available_plants_for_selection, # Par défaut, toutes les plantes sont sélectionnées
                    key="arrosage_multiselect"
                )
                
                # Les champs de quantité, durée, méthode, notes ont été retirés comme demandé.

                submitted_watering = st.form_submit_button("💧 Enregistrer cet arrosage")

                if submitted_watering:
                    if not selected_plants_for_watering:
                        st.warning("Veuillez sélectionner au moins une plante à arroser.")
                    else:
                        new_watering_event = {
                            "date": today, # Utilise le Timestamp 'today'
                            "plants": selected_plants_for_watering,
                            # Les champs amount_liters, duration_minutes, method, notes ne sont plus enregistrés
                        }
                        
                        journal["arrosages"].append(new_watering_event)
                        data_manager.sauvegarder_journal(journal)
                        
                        # Après l'arrosage, réinitialiser les déficits pour les familles des plantes choisies
                        for plant_name in selected_plants_for_watering: # Itérer sur les noms des plantes sélectionnées
                            if plant_name in plantes_index: # Vérifier que le nom de la plante est dans l'index principal des plantes
                                family_code = plantes_index[plant_name].get("famille") # Obtenir le code de la famille
                                if family_code and family_code in etat_jardin["deficits_accumules"]:
                                    etat_jardin["deficits_accumules"][family_code] = 0.0
                        data_manager.sauvegarder_etat_jardin(etat_jardin)
                        
                        st.success(f"💧 Arrosage enregistré pour {', '.join(selected_plants_for_watering)} !")
                        st.rerun() # Re-exécuter pour mettre à jour les données affichées

        with col_tonte:
            hauteur_tonte_input = st.slider("Hauteur après tonte (cm) :", constants.MIN_HAUTEUR_TONTE_SLIDER, constants.MAX_HAUTEUR_TONTE_SLIDER, hauteur_tonte_input_default, key="daily_tonte_hauteur")
            if st.button("✂️ J'ai tondu aujourd'hui", use_container_width=True):
                journal["tontes"].append({"date": today, "hauteur": hauteur_tonte_input})
                data_manager.sauvegarder_journal(journal)
                st.success(f"✂️ Tonte enregistrée à {hauteur_tonte_input} cm.")
                st.rerun()

        st.markdown("---")
        st.markdown("### Votre Historique Rapide")

        # Filtrer les entrées d'arrosage valides pour l'affichage de l'historique rapide
        valid_arrosages_for_display = [
            entry for entry in journal["arrosages"]
            if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], pd.Timestamp)
        ]

        if valid_arrosages_for_display:
            # Obtenir le dernier événement d'arrosage (maintenant un dictionnaire)
            latest_watering_event = max(valid_arrosages_for_display, key=lambda x: x["date"])
            plants_watered_str = ", ".join(latest_watering_event.get("plants", ["N/A"]))
            st.info(f"**Dernier arrosage :** {format_date(latest_watering_event['date'].date(), format='full', locale='fr')} pour **{plants_watered_str}**")
        else:
            st.info("**Aucun arrosage enregistré pour l'instant.**")

        if journal["tontes"]:
            valid_tontes = [tonte for tonte in journal["tontes"] if isinstance(tonte, dict) and "date" in tonte and isinstance(tonte["date"], pd.Timestamp)]
            if valid_tontes:
                derniere_tonte = max(valid_tontes, key=lambda x: x["date"])
                st.info(f"**Dernière tonte :** {format_date(derniere_tonte['date'].date(), format='full', locale='fr')} à {derniere_tonte['hauteur']} cm")
            else:
                st.info("**Aucune tonte valide enregistrée.**")
        else:
            st.info("**Aucune tonte enregistrée pour l'instant.**")

    with tab5:
        st.header("🌱 Mon Potager & Paramètres")

        # Sélection des plantes cultivées
        toutes_les_plantes = sorted(plantes_index.keys())
        plantes_choisies = st.multiselect(
            "Sélectionnez les **plantes cultivées** :",
            toutes_les_plantes,
            default=plantes_par_defaut,
            key="plantes_selection_tab5"
        )
        # Mettre à jour plantes_par_defaut pour les calculs globaux si modifié dans l'UI
        if plantes_choisies != plantes_par_defaut:
            plantes_par_defaut = plantes_choisies
            # Re-sauvegarder les préférences immédiatement si les plantes changent dans l'UI
            prefs["plantes"] = plantes_choisies
            data_manager.enregistrer_preferences_utilisateur(prefs)


        # Bouton de réinitialisation des paramètres
        if st.button("🔁 Réinitialiser les paramètres", key="reset_prefs_tab5"):
            data_manager.enregistrer_preferences_utilisateur({})
            data_manager.charger_preferences_utilisateur.clear()
            data_manager.charger_familles.clear()
            data_manager.charger_etat_jardin.clear()
            data_manager.charger_journal.clear() # Vider le cache du journal aussi lors d'une réinitialisation complète
            st.success("Paramètres réinitialisés ! Actualisation de la page...")
            st.rerun()

        st.markdown("---")
        st.subheader("📍 Lieu et Météo")

        # Entrée texte pour la ville
        ville = st.text_input("Ville ou commune (ex: Beauzelle) :", prefs.get("ville", "Beauzelle"), key="ville_input_tab5")
        
        # Mettre à jour les préférences avec la nouvelle ville si différente
        if ville != prefs.get("ville", "Beauzelle"):
            prefs["ville"] = ville
            data_manager.enregistrer_preferences_utilisateur(prefs)
            get_coords_from_city.clear() # Vider le cache pour les nouvelles coordonnées de la ville
            recuperer_meteo.clear() # Vider le cache météo pour la nouvelle ville
            st.rerun() # Re-exécuter pour appliquer le changement de ville

        infos_ville = get_coords_from_city(ville)

        if infos_ville:
            LAT = infos_ville["lat"]
            LON = infos_ville["lon"]
            st.info(f"📍 Ville sélectionnée : **{infos_ville['name']}**, {infos_ville['country']} \n"
                                     f"🌐 Coordonnées : `{LAT:.2f}, {LON:.2f}`")
        else:
            st.error("❌ Ville non trouvée. Veuillez vérifier l'orthographe ou en choisir une autre.")
            st.stop() # Arrêter l'exécution pour éviter les erreurs si la ville n'est pas trouvée

        # Récupérer les données météo pour cette ville
        df_meteo_global = recuperer_meteo(LAT, LON)
        if df_meteo_global.empty:
            st.warning("Impossible de récupérer les données météo. Certaines fonctionnalités seront limitées.")
            # st.stop() # Décidez si vous voulez arrêter ou simplement limiter les fonctionnalités

        # --- AJOUTER CES LIGNES POUR ASSURER LES TYPES NUMÉRIQUES ---
        df_meteo_global["temp_max"] = pd.to_numeric(df_meteo_global["temp_max"], errors='coerce')
        df_meteo_global["pluie"] = pd.to_numeric(df_meteo_global["pluie"], errors='coerce')
        df_meteo_global["evapo"] = pd.to_numeric(df_meteo_global["evapo"], errors='coerce')

        # Gérer les valeurs NaN potentielles qui pourraient résulter de 'coerce' si des données non numériques étaient présentes
        # Pour les données météo, remplir avec 0 ou une valeur par défaut raisonnable peut être approprié
        df_meteo_global = df_meteo_global.fillna(0) # Ou utiliser df_meteo_global.bfill().ffill() pour un remplissage plus sophistiqué

        st.markdown("---")
        st.subheader("🌍 Caractéristiques de votre sol")

        # Sélection du type de sol
        type_sol = st.selectbox("Type de sol :", ["Limoneux", "Sableux", "Argileux"],
                                    index=["Limoneux", "Sableux", "Argileux"].index(type_sol_defaut),
                                    key="type_sol_select_tab5")
        # Case à cocher pour le paillage
        paillage = st.checkbox("Présence de paillage", value=paillage_defaut, key="paillage_checkbox_tab5")

        # Sauvegarder les préférences (ville, plantes, sol, paillage)
        if (type_sol != type_sol_defaut) or (paillage != paillage_defaut):
            prefs.update({"plantes": plantes_choisies, "paillage": paillage, "type_sol": type_sol})
            data_manager.enregistrer_preferences_utilisateur(prefs)
            st.success("Vos préférences ont été enregistrées.")
            st.rerun() # Re-exécuter pour appliquer les nouveaux facteurs sol/paillage


        st.markdown("---")
        st.subheader("💧 Historique Arrosage")

        # Filtrer les entrées d'arrosage valides pour l'affichage de l'historique dans tab5
        valid_arrosages_tab5 = [
            entry for entry in journal["arrosages"]
            if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], pd.Timestamp)
        ]

        # Afficher le dernier arrosage enregistré ou un slider si aucun
        if valid_arrosages_tab5:
            # Obtenir l'événement du dernier arrosage (qui est maintenant un dictionnaire)
            date_dernier_arrosage_tab5_event = max(valid_arrosages_tab5, key=lambda x: x["date"])
            date_dernier_arrosage_tab5 = date_dernier_arrosage_tab5_event["date"]
            
            jours_depuis_tab5 = (today - date_dernier_arrosage_tab5).days
            plants_watered_str_tab5 = ", ".join(date_dernier_arrosage_tab5_event.get("plants", ["N/A"]))
            st.markdown(f"💧 **Dernier arrosage enregistré :** il y a **{jours_depuis_tab5} jour(s)** (le {format_date(date_dernier_arrosage_tab5.date(), locale='fr')}) pour **{plants_watered_str_tab5}**")
        else:
            # Slider pour simuler la date du dernier arrosage si le journal est vide
            jours_depuis_tab5 = st.slider("Jours depuis le dernier arrosage (pour simulation si aucun enregistré) :", 0, 14, constants.DEFAULT_JOURS_ARROSAGE_SIMULATION, key="jours_arrosage_slider_tab5")
            date_dernier_arrosage_tab5 = today - pd.Timedelta(days=jours_depuis_tab5)
            st.info(f"Simule le dernier arrosage au **{format_date(date_dernier_arrosage_tab5.date(), locale='fr')}**.")


        # Calculer les facteurs sol et paillage et les seuils de déficit
        facteur_sol = constants.FACTEUR_SOL.get(type_sol, 1.0)
        facteur_paillage = constants.FACTEUR_PAILLAGE_REDUCTION if paillage else 1.0
        SEUIL_DEFICIT = constants.SEUILS_DEFICIT_SOL.get(type_sol, 20)

        st.caption(f"Le seuil de déficit pour un sol **{type_sol.lower()}** est de **{SEUIL_DEFICIT} mm** (quantité d'eau manquante avant arrosage critique).")


        st.markdown("---")
        st.subheader("✂️ Historique Tonte")

        # Afficher la dernière tonte enregistrée ou un slider si aucune
        if journal["tontes"]:
            valid_tontes_tab5 = [t for t in journal["tontes"] if isinstance(t, dict) and "date" in t]
            if valid_tontes_tab5:
                date_dernier_tonte_tab5 = max(valid_tontes_tab5, key=lambda x: x["date"])["date"]
                jours_depuis_tonte_tab5 = (today - date_dernier_tonte_tab5).days
                st.markdown(f"✂️ **Dernière tonte enregistrée :** il y a **{jours_depuis_tonte_tab5} jour(s)** (le {format_date(date_dernier_tonte_tab5.date(), format='full', locale='fr')})")
            else:
                jours_depuis_tonte_tab5 = st.slider("Jours depuis la dernière tonte (pour simulation si aucune enregistrée) :", 1, 21, constants.DEFAULT_JOURS_TONTE_SIMULATION, key="jours_tonte_slider_tab5_empty")
                date_dernier_tonte_tab5 = today - pd.Timedelta(days=jours_depuis_tonte_tab5)
                st.info(f"Simule la dernière tonte au **{format_date(date_dernier_tonte_tab5.date(), format='full', locale='fr')}**.")
        else:
            jours_depuis_tonte_tab5 = st.slider("Jours depuis la dernière tonte (pour simulation si aucune enregistrée) :", 1, 21, constants.DEFAULT_JOURS_TONTE_SIMULATION, key="jours_tonte_slider_tab5")
            date_dernier_tonte_tab5 = today - pd.Timedelta(days=jours_depuis_tonte_tab5)
            st.info(f"Simule la dernière tonte au **{format_date(date_dernier_tonte_tab5.date(), format='full', locale='fr')}**.")

        # Slider pour la hauteur cible de la pelouse
        hauteur_cible_cm = st.slider("Hauteur cible de votre pelouse (cm) :", constants.MIN_HAUTEUR_TONTE_SLIDER, constants.MAX_HAUTEUR_TONTE_SLIDER, constants.DEFAULT_HAUTEUR_CIBLE_CM, key="hauteur_cible_slider_tab5")
        st.caption(f"Vous visez une hauteur de coupe de **{hauteur_cible_cm} cm** pour votre pelouse.")

        # Filtrer les données météo pour le calcul de la croissance de la tonte
        df_tonte_calc_period = df_meteo_global[(df_meteo_global["date"] >= date_dernier_tonte_tab5) & (df_meteo_global["date"] <= today)].copy()

    
    df_tonte_calc_period["croissance"] = df_tonte_calc_period.apply(
        lambda row: garden_logic.croissance_herbe(row["temp_max"], row["pluie"], row["evapo"]), axis=1
    )
    croissance_totale_mm = df_tonte_calc_period["croissance"].sum()

    hauteur_initiale_apres_tonte = hauteur_tonte_input_default # Utiliser la hauteur par défaut ou la dernière enregistrée
    hauteur_estimee_cm = hauteur_initiale_apres_tonte + (croissance_totale_mm / 10)

    # Recalculer les déficits pour le jour actuel en fonction des dernières informations et de la dernière mise à jour
    nouveaux_deficits = garden_logic.calculer_deficits_accumules(
        journal["arrosages"], # Passer le journal avec la nouvelle structure
        familles,
        plantes_choisies, # Utiliser plantes_choisies du multiselect pour l'exécution actuelle
        df_meteo_global,
        today,
        type_sol,
        paillage
    )
    
    # Mettre à jour l'état du jardin avec les déficits calculés aujourd'hui
    etat_jardin["date_derniere_maj"] = today
    etat_jardin["deficits_accumules"] = nouveaux_deficits
    data_manager.sauvegarder_etat_jardin(etat_jardin)

    # 🔥 Données d'alerte chaleur et pluie pour l'onglet 2
    df_futur_48h = df_meteo_global[(df_meteo_global["date"] > today) & (df_meteo_global["date"] <= today + pd.Timedelta(days=2))]
    jours_chauds_a_venir = (df_futur_48h["temp_max"] >= 30).sum()
    pluie_prochaine_48h_for_reco = df_futur_48h["pluie"].sum()

    # === 💡 CALCULER LES RECOMMANDATIONS PAR PLANTE ===
    table_data = []
    pluie_prochaine_24h = df_meteo_global[(df_meteo_global["date"] > today) & (df_meteo_global["date"] <= today + pd.Timedelta(days=1))]["pluie"].sum()

    for code_plante in plantes_choisies: # Utiliser plantes_choisies pour les recommandations
        if code_plante not in plantes_index:
            continue

        infos_plante = plantes_index[code_plante]
        code_famille = infos_plante["famille"]
        
        # Maintenant, nous utilisons le déficit CALCULÉ et SAUVEGARDÉ pour aujourd'hui
        deficit = nouveaux_deficits.get(code_famille, 0.0) # Le déficit est par famille

        if deficit <= 0:
            besoin, infos_bilan = False, f"✅ Excédent ou pas de déficit : {deficit:.1f} mm"
        elif deficit <= SEUIL_DEFICIT * 0.25:
            besoin, infos_bilan = False, f"🤏 Déficit très léger : {deficit:.1f} mm"
        elif deficit <= SEUIL_DEFICIT:
            if pluie_prochaine_24h >= deficit:
                besoin, infos_bilan = False, f"🌧️ Pluie prévue ({pluie_prochaine_24h:.1f} mm) dans 24h compensera"
            else:
                besoin, infos_bilan = False, f"🤏 Déficit léger : {deficit:.1f} mm"
        else: # deficit > SEUIL_DEFICIT
            if pluie_prochaine_48h_for_reco >= deficit:
                if deficit <= SEUIL_DEFICIT * 1.25:
                    besoin, infos_bilan = False, f"🌧️ Pluie prévue ({pluie_prochaine_48h_for_reco:.1f} mm) dans 48h compensera (Déficit actuel: {deficit:.1f} mm)"
                else:
                    besoin, infos_bilan = True, f"💧 Déficit critique : {deficit:.1f} mm (Pluie 48h: {pluie_prochaine_48h_for_reco:.1f} mm)"
            else:
                besoin, infos_bilan = True, f"💧 Déficit : {deficit:.1f} mm"

        table_data.append({
             "Plante": code_plante.capitalize(), # Afficher le nom de la plante
             "Recommandation": "Arroser" if besoin else "Pas besoin",
             "Couleur": "🟧" if besoin else "🟦",
             "Détail": infos_bilan
           })

    with tab2 :
        st.header("💧 Synthèse de mon Jardin")

        # Météo actuelle et alertes (en haut)
        st.markdown("### Météo Actuelle & Alertes")
        meteo_auj = df_meteo_global[df_meteo_global["date"] == today]
        if not meteo_auj.empty:
            temp = meteo_auj["temp_max"].values[0]
            pluie = meteo_auj["pluie"].values[0]

            col_meteo1, col_meteo2 = st.columns(2)
            with col_meteo1:
                st.metric(label="🌡️ Température Max Aujourd'hui", value=f"{temp}°C")
            with col_meteo2:
                st.metric(label="🌧️ Précipitations Aujourd'hui", value=f"{pluie:.1f} mm")

        if jours_chauds_a_venir >= 2:
            st.warning(f"🔥 **Alerte Chaleur :** {jours_chauds_a_venir} jour(s) avec ≥30°C à venir ! Pensez à l'hydratation.")
        if pluie_prochaine_48h_for_reco >= 10:
            st.info(f"🌧️ **Bonne nouvelle :** {pluie_prochaine_48h_for_reco:.1f} mm de pluie attendus dans les 48h. Peut-être pas besoin d'arroser !")

        st.markdown("---")

        # Recommandations générales (Arrosage, Tonte)
        st.markdown("### Recommandations Générales")
        col_reco1, col_reco2 = st.columns(2)

        with col_reco1:
            if any(p["Recommandation"] == "Arroser" for p in table_data):
                nb_plantes_a_arroser = sum(1 for p in table_data if p["Recommandation"] == "Arroser")
                st.error(f"💧 **Urgent ! {nb_plantes_a_arroser} plante(s) à arroser** aujourd'hui.")
            else:
                st.success("✅ **Pas besoin d'arroser** aujourd'hui.")

        with col_reco2:
            seuil_tonte_cm = hauteur_cible_cm * 1.5
            if hauteur_estimee_cm >= seuil_tonte_cm:
                st.warning(f"✂️ **Tonte recommandée :** Gazon estimé à {hauteur_estimee_cm:.1f} cm (cible {hauteur_cible_cm} cm).")
            else:
                st.success(f"🌱 **Pas besoin de tondre :** Gazon estimé à {hauteur_estimee_cm:.1f} cm (cible {hauteur_cible_cm} cm).")

        st.markdown("---")

        # Recommandations détaillées par plante
        st.markdown("### 🌱 Recommandations par Plante")
        for ligne in table_data:
            color_code = "#F8D7DA" if ligne["Recommandation"] == "Arroser" else "#D4EDDA"
            emoji = "💧" if ligne["Recommandation"] == "Arroser" else "✅"
            st.markdown(f"<div style='background-color: {color_code}; padding: 10px; border-radius: 5px; margin-bottom:5px;'>"
                                     f"{emoji} <b>{ligne['Plante']}</b> : {ligne['Détail']}</div>",
                                     unsafe_allow_html=True)

        st.markdown("---")

        # Prévisions
        st.markdown("### 📅 Prévisions du Potager")
        col_pred1, col_pred2 = st.columns(2)

        with col_pred1:
            arrosage_necessaire_aujourdhui = any(p["Recommandation"] == "Arroser" for p in table_data)
            if arrosage_necessaire_aujourdhui:
                st.warning("💧 **Arrosage nécessaire aujourd'hui** pour certaines plantes.")
            else:
                # La fonction estimer_arrosage_le_plus_contraignant prend journal["arrosages"] et retourne une date
                date_prochain_arrosage = garden_logic.estimer_arrosage_le_plus_contraignant(
                    plantes_choisies, # Utiliser plantes_choisies du multiselect pour l'exécution actuelle
                    plantes_index, # <-- Ajout de index_plantes
                    df_meteo_global[(df_meteo_global["date"] > today) & (df_meteo_global["date"] <= today + pd.Timedelta(days=constants.DEFAULT_JOURS_ARROSAGE_SIMULATION))], # Limiter la prévision
                    SEUIL_DEFICIT, # <-- Utilisation de la variable SEUIL_DEFICIT
                    facteur_sol, # <-- Utilisation de la variable facteur_sol
                    facteur_paillage # <-- Utilisation de la variable facteur_paillage
                )
                if date_prochain_arrosage:
                    nb_jours = (date_prochain_arrosage - today).days
                    message_jours = "aujourd'hui" if nb_jours == 0 else ("demain" if nb_jours == 1 else f"dans {nb_jours} jour(s)")
                    st.info(f"💧 **Prochain arrosage estimé :** {message_jours} ({format_date(date_prochain_arrosage.date(), format='medium', locale='fr')})")
                else:
                    st.success("✅ **Pas d'arrosage nécessaire** dans les 7 prochains jours.")

        with col_pred2:
            date_prochaine_tonte = garden_logic.estimer_date_prochaine_tonte(df_meteo_global[df_meteo_global["date"] > today], hauteur_estimee_cm, hauteur_cible_cm)
            if date_prochaine_tonte:
                st.info(f"✂️ **Prochaine tonte estimée :** {format_date(date_prochaine_tonte.date(), format='medium', locale='fr')}")
            else:
                st.success("🟢 **Pas de tonte prévue** dans les prochains jours.")

        st.markdown("---")
        st.subheader("📰 Recommandations du mois")
        reco_mois = recommendations_mensuelles.get(int(current_month))

        if reco_mois:
            st.subheader(f"{reco_mois['titre']} du mois")
            st.write("Voici quelques conseils pour votre jardin ce mois-ci :")
            for conseil in reco_mois["conseils"]:
                st.markdown(f"- {conseil}")
        else:
            st.info("Aucune recommandation spécifique disponible pour ce mois. Revenez le mois prochain !")

    with tab3:
        st.header("📈 Suivi Météo")

        st.subheader("Prévisions et Historique")

        df_a_afficher = df_meteo_global[(df_meteo_global["date"] >= today - pd.Timedelta(days=2)) & (df_meteo_global["date"] <= today + pd.Timedelta(days=7))]
        for _, row in df_a_afficher.iterrows():
            jour_texte = "Aujourd'hui" if row["date"].date() == today.date() else format_date(row["date"].date(), format='full', locale='fr')
            # Utilisez une icône météo simple basée sur les conditions (ex: soleil, pluie, nuage)
            # Ceci est un exemple, vous devrez peut-être étendre avec une vraie logique d'icônes météo
            icone_meteo = "☀️" if row["temp_max"] > 25 and row["pluie"] < 1 else ("🌧️" if row["pluie"] > 0 else "☁️")

            st.markdown(f"""
            <div style="background-color: {'#e0f7fa' if row['date'].date() == today.date() else '#f0f8ff'}; 
                                 border-left: 5px solid {'#007bff' if row['date'].date() == today.date() else '#ccc'};
                                 border-radius: 8px; padding: 10px; margin-bottom: 8px;
                                 display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <b>{jour_texte}</b><br>
                    <small>{format_date(row["date"].date(), format='dd MMM', locale='fr')}</small>
                </div>
                <div style="text-align: right;">
                    {icone_meteo} 🌡️ {row['temp_max']}°C<br>
                    💧 {row['pluie']:.1f} mm &nbsp; 🌬️ {int(row['vent']) if pd.notna(row['vent']) else '-'} km/h
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Visualisation Graphique")

        st.line_chart(df_meteo_global[["date", "temp_max"]].set_index("date"), y="temp_max", use_container_width=True)
        st.bar_chart(df_meteo_global[["date", "pluie"]].set_index("date"), y="pluie", use_container_width=True)

    # Calcul des statistiques
    # Ces fonctions devront être mises à jour dans ui_components.py pour gérer la nouvelle structure du journal
    stats_arrosage = ui_components.calculer_stats_arrosage(journal) 
    stats_tonte = ui_components.calculer_stats_tonte(journal)

    with tab4:
        st.header("📊 Historique & Statistiques du Jardin")

        st.markdown("### Calendrier de Votre Activité")
        ui_components.afficher_calendrier_frise(journal, today) # Cette fonction est clé ici

        st.markdown("---")

        st.markdown("### Aperçu Rapide de Votre Suivi")
        col_arrosage_stats, col_tonte_stats = st.columns(2) # Renommé pour éviter les conflits avec col_arrosage, col_tonte ci-dessus

        with col_arrosage_stats:
            st.markdown("#### 💧 Arrosages")
            st.metric(label="Total", value=stats_arrosage["nb_arrosages"])
            st.metric(label="Fréquence Moyenne", value=f"{stats_arrosage['freq_moyenne_jours']} jours")
            if stats_arrosage["dernier_arrosage_date"]:
                st.caption(f"Dernier : {format_date(stats_arrosage['dernier_arrosage_date'], format='medium', locale='fr')}")

        with col_tonte_stats:
            st.markdown("#### ✂️ Tontes")
            st.metric(label="Total", value=stats_tonte["nb_tontes"])
            st.metric(label="Fréquence Moyenne", value=f"{stats_tonte['freq_moyenne_jours']} jours")
            st.metric(label="Hauteur Moyenne", value=f"{stats_tonte['hauteur_moyenne']} cm")
            if stats_tonte["derniere_tonte_date"]:
                st.caption(f"Dernière : {format_date(stats_tonte['derniere_tonte_date'], format='medium', locale='fr')}")

        st.markdown("---")

        st.markdown("### Visualisation du Journal") # Ajout d'un titre pour plus de clarté

        # Afficher les événements d'arrosage
        st.markdown("#### Historique des Arrosages Détaillé")
        
        # Filtrer journal["arrosages"] pour s'assurer que toutes les entrées sont des dictionnaires bien formés
        # C'est une étape défensive pour éviter l'erreur "Lengths must match" si une entrée mal formée s'est glissée
        valid_journal_arrosages_for_display = [
            entry for entry in journal["arrosages"]
            if isinstance(entry, dict) and "date" in entry and isinstance(entry["date"], pd.Timestamp)
        ]

        # Créer un DataFrame à partir de la nouvelle structure d'arrosages
        arrosage_display_data = []
        for entry in valid_journal_arrosages_for_display: # Utiliser la liste filtrée ici
            arrosage_display_data.append({
                "Date": entry["date"].date(),
                "Plantes arrosées": ", ".join(entry.get("plants", ["N/A"])),
                # Les champs "Quantité (L)", "Durée (min)", "Méthode", "Notes" ne sont plus affichés
            })

        df_arrosages = pd.DataFrame(arrosage_display_data)
        if not df_arrosages.empty:
            st.dataframe(df_arrosages.sort_values(by="Date", ascending=False).set_index("Date"), use_container_width=True)
        else:
            st.info("Aucun arrosage enregistré.")

        # Afficher les événements de tonte (pas de changement nécessaire ici)
        st.markdown("#### Historique des Tontes")
        valid_tontes_for_df = [{"Date": t["date"].date(), "Hauteur (cm)": t["hauteur"]}
                               for t in journal["tontes"] if isinstance(t, dict) and "date" in t and "hauteur" in t and isinstance(t["date"], pd.Timestamp)]
        df_tontes = pd.DataFrame(valid_tontes_for_df)
        if not df_tontes.empty:
            st.dataframe(df_tontes.sort_values(by="Date", ascending=False).set_index("Date"), use_container_width=True)
        else:
            st.info("Aucune tonte enregistrée.")


except Exception as e:
    st.error(f"Une erreur générale est survenue : {e}")
    st.info("Veuillez vérifier vos fichiers de configuration (journal_jardin.json, parametres_utilisateur.json, familles_plantes.json, etat_jardin.json, recommandations_mensuelles.json) et votre connexion internet.")
