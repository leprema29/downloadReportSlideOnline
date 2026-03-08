# Slide to PDF - Téléchargeur de présentations en ligne

Outil Python pour télécharger des présentations hébergées en ligne (Adobe InDesign, etc.) et les convertir en un seul fichier PDF.

## Problème résolu

Les viewers en ligne comme `indd.adobe.com` ne proposent pas toujours de téléchargement direct. Cet outil automatise la capture de chaque slide avec un navigateur headless, en gérant :
- L'acceptation automatique des cookies
- L'attente du rendu complet de chaque slide (évite les pages blanches)
- La détection et le réessai des slides vides
- L'assemblage final en PDF

## Installation

```bash
# 1. Installer les dépendances Python
pip install -r requirements.txt

# 2. Installer le navigateur Chromium pour Playwright
playwright install chromium
```

## Utilisation

```bash
# Usage basique
python slide_to_pdf.py "https://indd.adobe.com/view/b2dc8260-1b73-4e96-b158-9a5831e129f7"

# Avec un nom de fichier de sortie personnalisé
python slide_to_pdf.py "https://indd.adobe.com/view/..." -o "Digital_2026_Cameroon.pdf"

# Avec un timeout plus long par slide (utile pour les connexions lentes)
python slide_to_pdf.py "https://indd.adobe.com/view/..." --timeout 15

# Garder les captures d'écran individuelles
python slide_to_pdf.py "https://indd.adobe.com/view/..." --keep-screenshots
```

## Options

| Option | Description | Défaut |
|---|---|---|
| `url` | URL de la présentation | (obligatoire) |
| `-o`, `--output` | Nom du fichier PDF de sortie | `slides_<slug>.pdf` |
| `--timeout` | Secondes d'attente par slide | 8 |
| `--retries` | Réessais pour les slides vides | 2 |
| `--keep-screenshots` | Garder les PNG individuels | Non |

## Prérequis

- Python 3.10+
- Playwright + Chromium
- Pillow
