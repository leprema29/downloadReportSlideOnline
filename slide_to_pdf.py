#!/usr/bin/env python3
"""
Télécharge les slides d'une présentation Adobe InDesign (indd.adobe.com)
et les assemble en un seul fichier PDF.

Usage:
    python slide_to_pdf.py <url> [options]

Exemples:
    python slide_to_pdf.py "https://indd.adobe.com/view/b2dc8260-1b73-4e96-b158-9a5831e129f7"
    python slide_to_pdf.py "https://indd.adobe.com/view/..." -o rapport.pdf --timeout 10
"""

import argparse
import re
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def parse_slide_count(page) -> int:
    """Parse le compteur de slides 'X sur Y' pour obtenir le nombre total."""
    try:
        # Cherche le texte du type "1 sur 82" ou "1 of 82" dans la barre de statut
        counter_text = page.locator("text=/\\d+\\s+(sur|of|de|von)\\s+\\d+/i").first.inner_text(timeout=10000)
        match = re.search(r"(\d+)\s+(?:sur|of|de|von)\s+(\d+)", counter_text, re.IGNORECASE)
        if match:
            return int(match.group(2))
    except Exception:
        pass
    return 0


def accept_cookies(page):
    """Accepte le bandeau de cookies s'il est présent."""
    cookie_selectors = [
        "text=Accepter",
        "text=Accept",
        "text=Accept All",
        "text=Tout accepter",
        "button:has-text('OK')",
        "button:has-text('Agree')",
    ]
    for selector in cookie_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                print("  -> Cookies acceptés")
                time.sleep(1)
                return True
        except Exception:
            continue
    return False


def wait_for_slide_content(page, timeout_sec: float = 8):
    """
    Attend que le contenu de la slide soit réellement rendu.
    Vérifie que les images/canvas/SVG dans la zone de slide sont chargés.
    """
    # Attente de base pour le rendu
    time.sleep(1.5)

    # Attend que le réseau soit au repos (pas de requêtes en cours)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_sec * 1000)
    except PlaywrightTimeout:
        pass

    # Attente supplémentaire pour le rendu visuel
    time.sleep(1)


def is_slide_blank(screenshot_path: Path, threshold: float = 0.97) -> bool:
    """
    Vérifie si une capture d'écran est principalement vide/blanche.
    Retourne True si plus de `threshold` des pixels sont quasi-blancs.
    """
    img = Image.open(screenshot_path).convert("L")  # Convertir en niveaux de gris
    pixels = list(img.getdata())
    total = len(pixels)
    # Compter les pixels très clairs (presque blancs, > 240)
    white_count = sum(1 for p in pixels if p > 240)
    ratio = white_count / total
    return ratio > threshold


def capture_slides(url: str, output_dir: Path, timeout_sec: float = 8, max_retries: int = 2):
    """Capture chaque slide en screenshot PNG."""
    screenshots = []

    with sync_playwright() as p:
        print("Lancement du navigateur...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,  # Haute résolution pour des captures nettes
        )
        page = context.new_page()

        print(f"Chargement de {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # Accepter les cookies
        accept_cookies(page)
        time.sleep(2)

        # Attendre le chargement initial
        wait_for_slide_content(page, timeout_sec)

        # Déterminer le nombre total de slides
        total_slides = parse_slide_count(page)
        if total_slides == 0:
            print("Impossible de détecter le nombre de slides. Utilisation du mode exploration.")
            total_slides = 200  # Limite de sécurité

        print(f"Nombre de slides détecté : {total_slides}")

        # Capturer chaque slide
        consecutive_blanks = 0
        for i in range(1, total_slides + 1):
            slide_path = output_dir / f"slide_{i:04d}.png"
            print(f"  Capture slide {i}/{total_slides}...", end="", flush=True)

            # Attendre le rendu de la slide
            wait_for_slide_content(page, timeout_sec)

            # Prendre la capture d'écran
            page.screenshot(path=str(slide_path), full_page=False)

            # Vérifier si la slide est vide et réessayer si nécessaire
            retry_count = 0
            while is_slide_blank(slide_path) and retry_count < max_retries:
                retry_count += 1
                print(f" (réessai {retry_count})...", end="", flush=True)
                time.sleep(3)
                wait_for_slide_content(page, timeout_sec)
                page.screenshot(path=str(slide_path), full_page=False)

            if is_slide_blank(slide_path):
                consecutive_blanks += 1
                print(" [VIDE - ignorée]")
                slide_path.unlink()  # Supprimer la capture vide
                if consecutive_blanks >= 5 and total_slides == 200:
                    print("  -> 5 slides vides consécutives, fin de la présentation.")
                    break
            else:
                consecutive_blanks = 0
                screenshots.append(slide_path)
                print(" OK")

            # Naviguer vers la slide suivante (flèche droite)
            if i < total_slides:
                # Essayer de cliquer sur le bouton "suivant"
                try:
                    next_btn = page.locator('[aria-label="Next"]').first
                    if next_btn.is_visible(timeout=1000):
                        next_btn.click()
                        continue
                except Exception:
                    pass

                # Fallback : touche flèche droite
                page.keyboard.press("ArrowRight")

        browser.close()

    return screenshots


def screenshots_to_pdf(screenshots: list[Path], output_pdf: Path):
    """Assemble les captures d'écran en un seul fichier PDF."""
    if not screenshots:
        print("Aucune slide capturée !")
        return False

    print(f"\nAssemblage de {len(screenshots)} slides en PDF...")

    images = []
    for path in screenshots:
        img = Image.open(path).convert("RGB")
        images.append(img)

    # Sauvegarder le PDF
    first_image = images[0]
    remaining = images[1:] if len(images) > 1 else []
    first_image.save(
        str(output_pdf),
        save_all=True,
        append_images=remaining,
        resolution=150,
    )

    print(f"PDF créé : {output_pdf} ({len(images)} pages)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Télécharge les slides d'une présentation en ligne et les assemble en PDF."
    )
    parser.add_argument("url", help="URL de la présentation (ex: https://indd.adobe.com/view/...)")
    parser.add_argument("-o", "--output", default=None, help="Nom du fichier PDF de sortie")
    parser.add_argument("--timeout", type=float, default=8, help="Timeout (sec) d'attente par slide (défaut: 8)")
    parser.add_argument("--retries", type=int, default=2, help="Nombre de réessais pour les slides vides (défaut: 2)")
    parser.add_argument("--keep-screenshots", action="store_true", help="Garder les captures d'écran individuelles")

    args = parser.parse_args()

    # Déterminer le nom de sortie
    if args.output:
        output_pdf = Path(args.output)
    else:
        # Extraire un nom depuis l'URL
        slug = args.url.rstrip("/").split("/")[-1][:20]
        output_pdf = Path(f"slides_{slug}.pdf")

    # Dossier temporaire pour les captures
    tmp_dir = Path("_tmp_slides")
    tmp_dir.mkdir(exist_ok=True)

    try:
        # Capture des slides
        screenshots = capture_slides(args.url, tmp_dir, args.timeout, args.retries)

        # Assemblage en PDF
        success = screenshots_to_pdf(screenshots, output_pdf)

        if success:
            print(f"\nTerminé ! Fichier : {output_pdf.resolve()}")
        else:
            print("\nÉchec : aucune slide n'a pu être capturée.")
            sys.exit(1)
    finally:
        # Nettoyage
        if not args.keep_screenshots and tmp_dir.exists():
            for f in tmp_dir.iterdir():
                f.unlink()
            tmp_dir.rmdir()
            print("Captures temporaires supprimées.")


if __name__ == "__main__":
    main()
