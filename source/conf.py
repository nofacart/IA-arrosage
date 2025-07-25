# Configuration file for the Sphinx documentation builder.

import os
import sys
sys.path.insert(0, os.path.abspath('..'))

# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'IA-arrosage'
copyright = '2025, Philippe CASTEL'
author = 'Philippe CASTEL'
release = 'v1.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon', # Pour les docstrings de style Google/NumPy
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'myst_parser', # Si vous voulez écrire certaines pages en Markdown
]

autodoc_default_options = {
    'members': True,
    'undoc-members': True, # Set to False if you only want to document things with docstrings
    'private-members': False,
    'show-inheritance': True,
}

templates_path = ['_templates']
exclude_patterns = []

language = 'fr'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
