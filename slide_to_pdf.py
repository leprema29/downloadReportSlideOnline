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
                time.sleep(1)
                return True
        except Exception:
            continue
    return False


def wait_for_slide_content(page, timeout_sec: float = 8):
    """Attend que le contenu de la slide soit réellement rendu."""
    time.sleep(1.5)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_sec * 1000)
    except PlaywrightTimeout:
        pass
    time.sleep(1)


def is_slide_blank(screenshot_path: Path, threshold: float = 0.97) -> bool:
    """Vérifie si une capture d'écran est principalement vide/blanche."""
    img = Image.open(screenshot_path).convert("L")
    pixels = list(img.getdata())
    total = len(pixels)
    white_count = sum(1 for p in pixels if p > 240)
    ratio = white_count / total
    return ratio > threshold


def capture_slides(url: str, output_dir: Path, timeout_sec: float = 8,
                   max_retries: int = 2, on_progress=None, cancel_event=None):
    """
    Capture chaque slide en screenshot PNG.

    on_progress: callback(event, data) pour signaler la progression.
        Événements:
        - "log": data = message string
        - "slide_total": data = nombre total de slides
        - "slide_captured": data = {"index": i, "total": total, "status": "ok"|"blank"|"retry", "path": path}
        - "done": data = liste des screenshots
    cancel_event: threading.Event, si set() le processus s'arrête.
    """
    screenshots = []

    def log(msg):
        if on_progress:
            on_progress("log", msg)
        print(msg)

    with sync_playwright() as p:
        log("Lancement du navigateur...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
        )
        page = context.new_page()

        log(f"Chargement de {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        accept_cookies(page)
        log("Cookies acceptés.")
        time.sleep(2)

        wait_for_slide_content(page, timeout_sec)

        total_slides = parse_slide_count(page)
        if total_slides == 0:
            log("Impossible de détecter le nombre de slides. Mode exploration activé.")
            total_slides = 200

        log(f"Nombre de slides détecté : {total_slides}")
        if on_progress:
            on_progress("slide_total", total_slides)

        consecutive_blanks = 0
        for i in range(1, total_slides + 1):
            if cancel_event and cancel_event.is_set():
                log("Capture annulée par l'utilisateur.")
                break

            slide_path = output_dir / f"slide_{i:04d}.png"
            log(f"  Capture slide {i}/{total_slides}...")

            wait_for_slide_content(page, timeout_sec)
            page.screenshot(path=str(slide_path), full_page=False)

            retry_count = 0
            while is_slide_blank(slide_path) and retry_count < max_retries:
                retry_count += 1
                log(f"    Réessai {retry_count}...")
                if on_progress:
                    on_progress("slide_captured", {"index": i, "total": total_slides, "status": "retry", "path": None})
                time.sleep(3)
                wait_for_slide_content(page, timeout_sec)
                page.screenshot(path=str(slide_path), full_page=False)

            if is_slide_blank(slide_path):
                consecutive_blanks += 1
                log(f"  Slide {i} [VIDE - ignorée]")
                if on_progress:
                    on_progress("slide_captured", {"index": i, "total": total_slides, "status": "blank", "path": None})
                slide_path.unlink()
                if consecutive_blanks >= 5 and total_slides == 200:
                    log("5 slides vides consécutives, fin de la présentation.")
                    break
            else:
                consecutive_blanks = 0
                screenshots.append(slide_path)
                log(f"  Slide {i} OK")
                if on_progress:
                    on_progress("slide_captured", {"index": i, "total": total_slides, "status": "ok", "path": str(slide_path)})

            if i < total_slides:
                try:
                    next_btn = page.locator('[aria-label="Next"]').first
                    if next_btn.is_visible(timeout=1000):
                        next_btn.click()
                        continue
                except Exception:
                    pass
                page.keyboard.press("ArrowRight")

        browser.close()

    if on_progress:
        on_progress("done", screenshots)

    return screenshots


def screenshots_to_pdf(screenshots: list[Path], output_pdf: Path,
                       optimize: bool = True, max_width: int = 1400,
                       jpeg_quality: int = 60, on_progress=None):
    """
    Assemble les captures d'écran en un seul fichier PDF optimisé.

    optimize: active la compression (redimensionnement + JPEG)
    max_width: largeur max en pixels (les images plus larges sont réduites)
    jpeg_quality: qualité JPEG (1-95, plus bas = plus petit fichier)
    """
    if not screenshots:
        if on_progress:
            on_progress("log", "Aucune slide capturée !")
        print("Aucune slide capturée !")
        return False

    msg = f"Assemblage de {len(screenshots)} slides en PDF..."
    if on_progress:
        on_progress("log", msg)
    print(msg)

    images = []
    for path in screenshots:
        img = Image.open(path).convert("RGB")

        if optimize:
            # Redimensionner si l'image est trop large
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)

        images.append(img)

    first_image = images[0]
    remaining = images[1:] if len(images) > 1 else []

    # Sauvegarder avec compression optimisée
    save_kwargs = {
        "save_all": True,
        "append_images": remaining,
    }

    if optimize:
        save_kwargs["resolution"] = 72  # 72 DPI pour publication en ligne
        save_kwargs["optimize"] = True
    else:
        save_kwargs["resolution"] = 150

    first_image.save(str(output_pdf), **save_kwargs)

    file_size = output_pdf.stat().st_size
    size_mb = file_size / (1024 * 1024)
    result_msg = f"PDF créé : {output_pdf} ({len(images)} pages, {size_mb:.1f} Mo)"
    if on_progress:
        on_progress("log", result_msg)
    print(result_msg)
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
    parser.add_argument("--no-optimize", action="store_true", help="Désactiver l'optimisation de taille du PDF")

    args = parser.parse_args()

    if args.output:
        output_pdf = Path(args.output)
    else:
        slug = args.url.rstrip("/").split("/")[-1][:20]
        output_pdf = Path(f"slides_{slug}.pdf")

    tmp_dir = Path("_tmp_slides")
    tmp_dir.mkdir(exist_ok=True)

    try:
        screenshots = capture_slides(args.url, tmp_dir, args.timeout, args.retries)
        success = screenshots_to_pdf(screenshots, output_pdf, optimize=not args.no_optimize)

        if success:
            print(f"\nTerminé ! Fichier : {output_pdf.resolve()}")
        else:
            print("\nÉchec : aucune slide n'a pu être capturée.")
            sys.exit(1)
    finally:
        if not args.keep_screenshots and tmp_dir.exists():
            for f in tmp_dir.iterdir():
                f.unlink()
            tmp_dir.rmdir()
            print("Captures temporaires supprimées.")


if __name__ == "__main__":
    main()
