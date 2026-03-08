#!/usr/bin/env python3
"""
Interface graphique professionnelle pour SlideToDF.
Télécharge les slides d'une présentation en ligne et les assemble en PDF.
"""

import json
import os
import platform
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk

from slide_to_pdf import capture_slides, screenshots_to_pdf

# --- Configuration ---
HISTORY_FILE = Path.home() / ".slidetodf_history.json"
APP_NAME = "SlideToDF"
APP_VERSION = "1.0"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class HistoryManager:
    """Gère l'historique des téléchargements."""

    def __init__(self, path: Path = HISTORY_FILE):
        self.path = path
        self.entries = self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def save(self):
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, url: str, output: str, slide_count: int, status: str):
        self.entries.insert(0, {
            "url": url,
            "output": output,
            "slides": slide_count,
            "status": status,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        # Garder les 50 dernières entrées
        self.entries = self.entries[:50]
        self.save()


class ThumbnailGrid(ctk.CTkScrollableFrame):
    """Grille de miniatures des slides capturées."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.thumbnails = []
        self.thumb_labels = []
        self.columns = 5
        self.thumb_size = (140, 80)

    def clear(self):
        for label in self.thumb_labels:
            label.destroy()
        self.thumb_labels.clear()
        self.thumbnails.clear()

    def add_thumbnail(self, image_path: str):
        try:
            img = Image.open(image_path)
            img.thumbnail(self.thumb_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.thumbnails.append(photo)

            idx = len(self.thumb_labels)
            row = idx // self.columns
            col = idx % self.columns

            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.grid(row=row, column=col, padx=4, pady=4)

            label = ctk.CTkLabel(frame, image=photo, text="")
            label.pack()

            num_label = ctk.CTkLabel(frame, text=f"#{idx + 1}",
                                     font=ctk.CTkFont(size=10),
                                     text_color="gray")
            num_label.pack()

            self.thumb_labels.append(frame)
        except Exception:
            pass


class LogConsole(ctk.CTkTextbox):
    """Console de logs avec horodatage."""

    def __init__(self, master, **kwargs):
        super().__init__(master, state="disabled", **kwargs)
        self.configure(font=ctk.CTkFont(family="Consolas", size=12))

    def log(self, message: str, tag: str = "info"):
        self.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.insert("end", f"[{timestamp}] {message}\n")
        self.see("end")
        self.configure(state="disabled")

    def clear(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


class HistoryWindow(ctk.CTkToplevel):
    """Fenêtre d'historique des téléchargements."""

    def __init__(self, master, history: HistoryManager, on_redownload=None):
        super().__init__(master)
        self.title("Historique des téléchargements")
        self.geometry("700x450")
        self.history = history
        self.on_redownload = on_redownload

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkLabel(self, text="Historique des téléchargements",
                              font=ctk.CTkFont(size=18, weight="bold"))
        header.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # Table
        table_frame = ctk.CTkScrollableFrame(self)
        table_frame.grid(row=1, column=0, padx=15, pady=10, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)

        if not history.entries:
            ctk.CTkLabel(table_frame, text="Aucun téléchargement enregistré.",
                         text_color="gray").pack(pady=30)
        else:
            for i, entry in enumerate(history.entries):
                row = ctk.CTkFrame(table_frame, fg_color=("gray90", "gray17") if i % 2 == 0 else ("white", "gray20"))
                row.pack(fill="x", padx=2, pady=1)
                row.grid_columnconfigure(1, weight=1)

                # Date
                ctk.CTkLabel(row, text=entry.get("date", "?"),
                             font=ctk.CTkFont(size=11), width=120).grid(row=0, column=0, padx=8, pady=6)

                # URL (tronquée)
                url_text = entry.get("url", "?")
                if len(url_text) > 50:
                    url_text = url_text[:50] + "..."
                ctk.CTkLabel(row, text=url_text,
                             font=ctk.CTkFont(size=11), anchor="w").grid(row=0, column=1, padx=4, pady=6, sticky="w")

                # Slides
                ctk.CTkLabel(row, text=f"{entry.get('slides', '?')} slides",
                             font=ctk.CTkFont(size=11), width=70).grid(row=0, column=2, padx=4, pady=6)

                # Status
                status = entry.get("status", "?")
                color = "#2ecc71" if status == "OK" else "#e74c3c"
                ctk.CTkLabel(row, text=status, text_color=color,
                             font=ctk.CTkFont(size=11, weight="bold"), width=50).grid(row=0, column=3, padx=4, pady=6)

                # Bouton re-télécharger
                if self.on_redownload:
                    url_val = entry.get("url", "")
                    btn = ctk.CTkButton(row, text="Relancer", width=70, height=26,
                                        font=ctk.CTkFont(size=11),
                                        command=lambda u=url_val: self._redownload(u))
                    btn.grid(row=0, column=4, padx=8, pady=6)

        # Bouton fermer
        ctk.CTkButton(self, text="Fermer", command=self.destroy, width=100).grid(
            row=2, column=0, pady=10)

    def _redownload(self, url):
        if self.on_redownload:
            self.on_redownload(url)
            self.destroy()


class App(ctk.CTk):
    """Application principale SlideToDF."""

    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION} — Téléchargeur de Présentations")
        self.geometry("950x750")
        self.minsize(800, 650)

        self.history = HistoryManager()
        self.cancel_event = threading.Event()
        self.is_running = False
        self.start_time = None
        self.timer_after_id = None
        self.captured_count = 0
        self.total_slides = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)  # Log console expands
        self.grid_rowconfigure(4, weight=1)  # Thumbnails expand

        self._build_header()
        self._build_config_section()
        self._build_controls()
        self._build_log_console()
        self._build_thumbnails()
        self._build_status_bar()

    # --- UI Construction ---

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(header, text=f"{APP_NAME}",
                             font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(header, text="Téléchargeur de présentations en ligne vers PDF",
                                font=ctk.CTkFont(size=13), text_color="gray")
        subtitle.grid(row=1, column=0, sticky="w")

        # Boutons header
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, rowspan=2, sticky="e")

        self.theme_btn = ctk.CTkButton(btn_frame, text="Thème clair", width=100,
                                       height=28, font=ctk.CTkFont(size=11),
                                       fg_color="gray30", command=self._toggle_theme)
        self.theme_btn.pack(side="left", padx=5)

        history_btn = ctk.CTkButton(btn_frame, text="Historique", width=100,
                                    height=28, font=ctk.CTkFont(size=11),
                                    fg_color="gray30", command=self._show_history)
        history_btn.pack(side="left", padx=5)

    def _build_config_section(self):
        config = ctk.CTkFrame(self)
        config.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        config.grid_columnconfigure(1, weight=1)

        # URL
        ctk.CTkLabel(config, text="URL de la présentation",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=15, pady=(12, 2), sticky="w", columnspan=2)

        url_frame = ctk.CTkFrame(config, fg_color="transparent")
        url_frame.grid(row=1, column=0, columnspan=3, padx=15, pady=(0, 8), sticky="ew")
        url_frame.grid_columnconfigure(0, weight=1)

        self.url_var = ctk.StringVar()
        self.url_entry = ctk.CTkEntry(url_frame, textvariable=self.url_var,
                                      placeholder_text="https://indd.adobe.com/view/...",
                                      height=36, font=ctk.CTkFont(size=13))
        self.url_entry.grid(row=0, column=0, sticky="ew")

        paste_btn = ctk.CTkButton(url_frame, text="Coller", width=70, height=36,
                                  command=self._paste_url)
        paste_btn.grid(row=0, column=1, padx=(8, 0))

        # Ligne 2 : Fichier de sortie + Dossier
        ctk.CTkLabel(config, text="Fichier de sortie",
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=15, pady=(5, 2), sticky="w")

        self.output_var = ctk.StringVar()
        self.output_entry = ctk.CTkEntry(config, textvariable=self.output_var,
                                         placeholder_text="(auto-généré depuis l'URL)",
                                         height=32)
        self.output_entry.grid(row=3, column=0, padx=15, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(config, text="Dossier de destination",
                     font=ctk.CTkFont(size=12)).grid(row=2, column=1, padx=15, pady=(5, 2), sticky="w")

        dir_frame = ctk.CTkFrame(config, fg_color="transparent")
        dir_frame.grid(row=3, column=1, columnspan=2, padx=15, pady=(0, 8), sticky="ew")
        dir_frame.grid_columnconfigure(0, weight=1)

        self.dir_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.dir_entry = ctk.CTkEntry(dir_frame, textvariable=self.dir_var, height=32)
        self.dir_entry.grid(row=0, column=0, sticky="ew")

        browse_btn = ctk.CTkButton(dir_frame, text="Parcourir...", width=90, height=32,
                                   command=self._browse_dir)
        browse_btn.grid(row=0, column=1, padx=(8, 0))

        # Ligne 3 : Options avancées
        opts = ctk.CTkFrame(config, fg_color="transparent")
        opts.grid(row=4, column=0, columnspan=3, padx=15, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(opts, text="Timeout (s) :", font=ctk.CTkFont(size=12)).pack(side="left")
        self.timeout_var = ctk.IntVar(value=8)
        ctk.CTkEntry(opts, textvariable=self.timeout_var, width=50, height=30).pack(side="left", padx=(4, 15))

        ctk.CTkLabel(opts, text="Tentatives :", font=ctk.CTkFont(size=12)).pack(side="left")
        self.retries_var = ctk.IntVar(value=2)
        ctk.CTkEntry(opts, textvariable=self.retries_var, width=50, height=30).pack(side="left", padx=(4, 15))

        self.keep_screenshots_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Conserver les captures PNG",
                        variable=self.keep_screenshots_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(15, 0))

    def _build_controls(self):
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        controls.grid_columnconfigure(1, weight=1)

        self.start_btn = ctk.CTkButton(controls, text="Démarrer la capture",
                                       height=40, font=ctk.CTkFont(size=14, weight="bold"),
                                       fg_color="#2ecc71", hover_color="#27ae60",
                                       command=self._start_capture)
        self.start_btn.grid(row=0, column=0, padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(controls, text="Annuler", height=40,
                                        font=ctk.CTkFont(size=14),
                                        fg_color="#e74c3c", hover_color="#c0392b",
                                        state="disabled", command=self._cancel_capture)
        self.cancel_btn.grid(row=0, column=1, sticky="w")

        # Barre de progression
        progress_frame = ctk.CTkFrame(controls, fg_color="transparent")
        progress_frame.grid(row=1, column=0, columnspan=3, pady=(10, 0), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=18)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(progress_frame, text="Prêt",
                                           font=ctk.CTkFont(size=12))
        self.progress_label.grid(row=0, column=1, padx=(10, 0))

    def _build_log_console(self):
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.grid(row=3, column=0, padx=20, pady=(5, 2), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Console",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w")

        self.log_console = LogConsole(log_frame, height=120)
        self.log_console.grid(row=1, column=0, sticky="nsew")

    def _build_thumbnails(self):
        thumb_frame = ctk.CTkFrame(self, fg_color="transparent")
        thumb_frame.grid(row=4, column=0, padx=20, pady=(2, 5), sticky="nsew")
        thumb_frame.grid_columnconfigure(0, weight=1)
        thumb_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(thumb_frame, text="Aperçu des slides",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w")

        self.thumbnail_grid = ThumbnailGrid(thumb_frame, height=130)
        self.thumbnail_grid.grid(row=1, column=0, sticky="nsew")

    def _build_status_bar(self):
        status_bar = ctk.CTkFrame(self, height=30, corner_radius=0,
                                  fg_color=("gray85", "gray15"))
        status_bar.grid(row=5, column=0, sticky="ew")
        status_bar.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(status_bar, text="Prêt",
                                         font=ctk.CTkFont(size=11),
                                         text_color=("gray30", "gray70"))
        self.status_label.grid(row=0, column=0, padx=15, pady=3)

        self.timer_label = ctk.CTkLabel(status_bar, text="",
                                        font=ctk.CTkFont(size=11),
                                        text_color=("gray30", "gray70"))
        self.timer_label.grid(row=0, column=2, padx=15, pady=3)

    # --- Actions ---

    def _paste_url(self):
        try:
            text = self.clipboard_get()
            self.url_var.set(text.strip())
        except Exception:
            pass

    def _browse_dir(self):
        from tkinter import filedialog
        directory = filedialog.askdirectory(initialdir=self.dir_var.get())
        if directory:
            self.dir_var.set(directory)

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("light")
            self.theme_btn.configure(text="Thème sombre")
        else:
            ctk.set_appearance_mode("dark")
            self.theme_btn.configure(text="Thème clair")

    def _show_history(self):
        HistoryWindow(self, self.history, on_redownload=self._redownload_from_history)

    def _redownload_from_history(self, url):
        self.url_var.set(url)
        self._start_capture()

    def _set_running(self, running: bool):
        self.is_running = running
        if running:
            self.start_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            self.url_entry.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self.url_entry.configure(state="normal")

    def _update_timer(self):
        if self.is_running and self.start_time:
            elapsed = int(time.time() - self.start_time)
            mins, secs = divmod(elapsed, 60)
            self.timer_label.configure(text=f"Temps écoulé : {mins:02d}:{secs:02d}")
            self.timer_after_id = self.after(1000, self._update_timer)

    def _start_capture(self):
        url = self.url_var.get().strip()
        if not url:
            self.log_console.log("Veuillez saisir une URL.")
            return

        self.cancel_event.clear()
        self._set_running(True)
        self.log_console.clear()
        self.thumbnail_grid.clear()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Démarrage...")
        self.status_label.configure(text="Capture en cours...")
        self.captured_count = 0
        self.total_slides = 0
        self.start_time = time.time()
        self._update_timer()

        # Déterminer le chemin de sortie
        output_name = self.output_var.get().strip()
        if not output_name:
            slug = url.rstrip("/").split("/")[-1][:20]
            output_name = f"slides_{slug}.pdf"
        if not output_name.endswith(".pdf"):
            output_name += ".pdf"

        dest_dir = Path(self.dir_var.get().strip())
        dest_dir.mkdir(parents=True, exist_ok=True)
        output_pdf = dest_dir / output_name

        timeout = self.timeout_var.get()
        retries = self.retries_var.get()
        keep = self.keep_screenshots_var.get()

        thread = threading.Thread(target=self._run_capture,
                                  args=(url, output_pdf, timeout, retries, keep),
                                  daemon=True)
        thread.start()

    def _run_capture(self, url, output_pdf, timeout, retries, keep_screenshots):
        tmp_dir = Path("_tmp_slides")
        tmp_dir.mkdir(exist_ok=True)
        status = "OK"
        slide_count = 0

        try:
            screenshots = capture_slides(
                url, tmp_dir, timeout, retries,
                on_progress=self._on_progress,
                cancel_event=self.cancel_event,
            )
            slide_count = len(screenshots)

            if self.cancel_event.is_set():
                status = "Annulé"
                self.after(0, lambda: self._on_complete(False, "Capture annulée."))
            elif screenshots:
                success = screenshots_to_pdf(screenshots, output_pdf,
                                             optimize=True, on_progress=self._on_progress)
                if success:
                    self.after(0, lambda: self._on_complete(True, str(output_pdf)))
                else:
                    status = "Erreur"
                    self.after(0, lambda: self._on_complete(False, "Erreur lors de la création du PDF."))
            else:
                status = "Erreur"
                self.after(0, lambda: self._on_complete(False, "Aucune slide capturée."))
        except Exception as e:
            status = "Erreur"
            self.after(0, lambda: self._on_complete(False, f"Erreur : {e}"))
        finally:
            self.history.add(url, str(output_pdf), slide_count, status)
            if not keep_screenshots and tmp_dir.exists():
                for f in tmp_dir.iterdir():
                    f.unlink()
                try:
                    tmp_dir.rmdir()
                except OSError:
                    pass

    def _on_progress(self, event: str, data):
        """Callback appelé depuis le thread de capture."""
        if event == "log":
            self.after(0, lambda d=data: self.log_console.log(d))
        elif event == "slide_total":
            self.total_slides = data
            self.after(0, lambda d=data: self.progress_label.configure(text=f"0/{d} slides"))
        elif event == "slide_captured":
            idx = data["index"]
            total = data["total"]
            status = data["status"]
            if status == "ok":
                self.captured_count += 1
                progress = idx / total if total > 0 else 0
                self.after(0, lambda p=progress, i=idx, t=total: self._update_progress(p, i, t))
                if data.get("path"):
                    self.after(0, lambda p=data["path"]: self.thumbnail_grid.add_thumbnail(p))

    def _update_progress(self, progress, current, total):
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{current}/{total} slides")

    def _on_complete(self, success: bool, message: str):
        self._set_running(False)
        if self.timer_after_id:
            self.after_cancel(self.timer_after_id)
            self.timer_after_id = None

        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        mins, secs = divmod(elapsed, 60)

        if success:
            self.progress_bar.set(1.0)
            self.status_label.configure(text=f"Terminé - {self.captured_count} slides en {mins:02d}:{secs:02d}")
            self.log_console.log(f"Terminé ! Fichier : {message}")

            # Boutons d'action post-capture
            result_frame = ctk.CTkFrame(self, fg_color="transparent")
            result_frame.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")

            output_path = Path(message)
            size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0

            ctk.CTkLabel(result_frame,
                         text=f"PDF : {output_path.name} ({size_mb:.1f} Mo)",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 15))

            ctk.CTkButton(result_frame, text="Ouvrir le PDF", width=120, height=30,
                          command=lambda: self._open_file(message)).pack(side="left", padx=5)

            ctk.CTkButton(result_frame, text="Ouvrir le dossier", width=120, height=30,
                          fg_color="gray30",
                          command=lambda: self._open_folder(str(output_path.parent))).pack(side="left", padx=5)
        else:
            self.status_label.configure(text=f"Erreur - {message}")
            self.log_console.log(message)

    def _cancel_capture(self):
        self.cancel_event.set()
        self.log_console.log("Annulation demandée...")
        self.status_label.configure(text="Annulation en cours...")

    @staticmethod
    def _open_file(path):
        path = str(path)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    @staticmethod
    def _open_folder(path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
