🌱 Arrosage Potager – Automatisation avec Météo
Ce script Python utilise les données météo de Open-Meteo pour estimer si un potager a besoin d’être arrosé, en se basant sur les 7 jours précédents et les 3 jours à venir.

📌 Fonctionnalités
🔍 Analyse de la température max et des précipitations sur 10 jours (7 passés + 3 futurs)

💧 Détermination automatique du besoin d’arrosage

📝 Génération quotidienne d’un rapport texte (rapport_arrosage_openmeteo.txt)

☁️ Exécution automatique via GitHub Actions tous les jours à 10h (heure de Paris)

⚙️ Fichiers
Fichier	Rôle
arrosage_potager_openmeteo.py	Script principal Python
rapport_arrosage_openmeteo.txt	Rapport généré automatiquement chaque jour
.github/workflows/arrosage.yml	Tâche GitHub Actions planifiée pour l'automatisation

🚀 Utilisation locale (optionnel)
Tu peux exécuter le script en local avec Python ≥ 3.8 :

bash
Copier
Modifier
pip install requests
python arrosage_potager_openmeteo.py
🤖 Automatisation avec GitHub Actions
Le script s'exécute automatiquement tous les jours à 10h via GitHub Actions et met à jour le rapport dans le dépôt.

📊 Exemple de conclusion générée
💧 Il faut arroser votre jardin si vous avez arrosé il y a plus de 3 jours.

Ce seuil est déterminé automatiquement selon les conditions météo (chaleur, pluie…).

🔧 Personnalisation
Tu peux ajuster :

La localisation (latitude, longitude)

Le seuil de chaleur ou de précipitations

Le format du rapport

📄 Licence
Projet personnel – libre d’usage non commercial.
Auteur : [NoFacArt]
