# constants.py

import os

# Base directory for data files (assuming constants.py is in the project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAM_PATH = os.path.join(BASE_DIR, "parametres_utilisateur.json")
JOURNAL_PATH = os.path.join(BASE_DIR, "journal_jardin.json")
ETAT_JARDIN_FILE = os.path.join(BASE_DIR, "etat_jardin.json")
FAMILLES_PLANTES_FILE = os.path.join(BASE_DIR, "familles_plantes.json")
RECOMMANDATIONS_FILE = os.path.join(BASE_DIR, "recommandations_jardin.json")
METEO_HISTORIQUE_DISPONIBLE = 7

# --- Default Values & Simulation ---
DEFAULT_JOURS_ARROSAGE_SIMULATION = 7 # For initial simulation if no watering recorded
DEFAULT_JOURS_TONTE_SIMULATION = 14 # For initial simulation if no mowing recorded
DEFAULT_HAUTEUR_CIBLE_CM = 5 # Default target height for lawn mowing in cm
# Added the missing constant:
DEFAULT_HAUTEUR_TONTE_INPUT = DEFAULT_HAUTEUR_CIBLE_CM # Default height for the mowing input slider
DEFAULT_ARROSAGE_VOLUME_MM = 10 # Default watering amount in mm when recording
METEO_HISTORIQUE_DISPONIBLE = 7 # Number of past days for which weather data is retrieved

# --- Slider Ranges for UI ---
MIN_HAUTEUR_TONTE_SLIDER = 2 # Minimum height for mowing slider in cm
MAX_HAUTEUR_TONTE_SLIDER = 8 # Maximum height for mowing slider in cm

# --- Garden Logic Factors ---
# Factors for soil type (affecting water retention and deficit thresholds)
FACTEUR_SOL = {
    "Sableux": 1.2,  # Sands drain faster, so higher factor might mean more frequent need
    "Limoneux": 1.0, # Baseline
    "Argileux": 0.8, # Clays retain water, so lower factor
}

# Thresholds for accumulated deficit (in mm) before critical watering is needed
SEUILS_DEFICIT_SOL = {
    "Sableux": 15, # Lower threshold for sandy soil (dries faster)
    "Limoneux": 20, # Medium threshold
    "Argileux": 25, # Higher threshold for clayey soil (retains more water)
}

# Factor for mulching (reduces evaporation)
FACTEUR_PAILLAGE_REDUCTION = 0.7 # 30% reduction in ET0 effect, for example

# --- Plant-specific constants (if needed, or defined in familles_plantes.json) ---
# Example: coefficients_kc = {"Tomate": 0.8, "Salade": 0.7} etc.
# These are typically in familles_plantes.json