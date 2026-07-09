#!/usr/bin/env python3
"""
Transcription Vocale FR — Application de bureau.

Interface graphique moderne (PySide6) pour transcrire de la voix française
en texte, en local et à haute précision (faster-whisper large-v3).

Fonctionnalités :
  • Glisser-déposer un fichier audio/vidéo, ou cliquer pour parcourir.
  • Transcription en arrière-plan (interface fluide, annulable).
  • Affichage du texte, copie et enregistrement (.txt / .srt) en un clic.
  • Trois thèmes : Sombre, Clair, Halloween.

L'application est pensée pour être simple d'utilisation par n'importe qui.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QProcess, QSettings, QThread, QObject, QTimer
from PySide6.QtGui import (
    QGuiApplication, QIcon, QPixmap, QPainter, QColor, QPen, QDesktopServices,
)
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QFileDialog, QFrame, QProgressBar,
    QMessageBox, QComboBox, QSizePolicy, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
)

from transcriber_core import (
    is_media_file, MEDIA_EXTS, APP_ROOT, RESOURCE_ROOT,
    load_corrections, save_corrections,
)
from version import __version__, RELEASES_API, RELEASES_PAGE


APP_NAME = "Transcription Vocale FR"


# =========================================================================== #
#  INTERNATIONALISATION (Anglais par défaut, Français en option)
# =========================================================================== #
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "French Voice Transcription",
        "subtitle": "High-accuracy French transcription, 100% on-device.",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "theme_halloween": "Halloween",
        "lang_button": "FR",
        "lang_button_tip": "Switch to French",
        "drop_title": "Drag an audio file here",
        "drop_sub": "or click to browse  ·  MP3, WAV, M4A, MP4…",
        "no_file": "No file selected",
        "quality_max": "Best quality (large-v3)",
        "quality_fast": "Fast (medium)",
        "quality_tip": "large-v3 = best accuracy. medium = faster.",
        "transcribe": "Transcribe",
        "cancel": "Cancel",
        "section_text": "Transcribed text",
        "copy": "Copy",
        "save": "Save",
        "placeholder": "The transcribed text will appear here as it is produced…",
        "ready": "Ready.",
        "file_ready": "File ready. Click “Transcribe”.",
        "initializing": "Initializing…",
        "cancelling": "Cancelling…",
        "copied": "Text copied to clipboard.",
        "saved": "Saved: {path}",
        "cancelled": "Transcription cancelled.",
        "failed_status": "Transcription failed.",
        "loading_model": "Loading model «{model}» (compute={compute}, threads={threads})…",
        "downloading_model": "First run: the model is downloading (~3 GB). This may take several minutes.",
        "transcribing": "Transcribing…",
        "model_ready": "Model ready in {sec:.1f}s.",
        "lang_info": "Language: {lang} (prob. {prob:.2f}) — {dur:.1f}s",
        "done_status": "Done in {sec:.1f}s · {segs} segments · {dur:.1f}s of audio ({ratio:.2f}× real time).",
        "browse_title": "Choose an audio/video file",
        "media_filter": "Media files",
        "all_files": "All files",
        "save_title": "Save transcription",
        "text_filter": "Text file",
        "srt_filter": "Subtitles",
        "error": "Error",
        "save_error": "Failed to save:\n{err}",
        "transcribe_error": "Transcription failed:\n\n{err}",
        "corrections": "Corrections",
        "corrections_tip": "Custom word replacements (e.g. “Volio” → “Voelio”).",
        "corr_title": "Vocabulary corrections",
        "corr_intro": "When the app mishears a word, add a correction here. "
                      "It is applied automatically to every transcription.",
        "corr_col_heard": "Heard (wrong)",
        "corr_col_fixed": "Replace with",
        "corr_add": "Add",
        "corr_remove": "Remove",
        "corr_save": "Save",
        "corr_close": "Close",
        "corr_saved": "Corrections saved.",
        "corr_placeholder_from": "e.g. Volio",
        "corr_placeholder_to": "e.g. Voelio",
        "corr_count": "{n} correction(s)",
        "diarize": "Identify speakers",
        "diarize_tip": "Detect turn-taking in a conversation (Speaker 1, 2…). "
                       "Lightweight, pause-based heuristic.",
        "no_audio": "This file has no audio track (video-only?). "
                    "Please provide a file that contains sound.",
        "update_check": "Check for updates",
        "update_checking": "Checking for updates…",
        "update_available_title": "Update available",
        "update_available": "A new version is available: {new} "
                            "(you have {cur}).\n\nUpdate now? "
                            "The app will download and install it automatically.",
        "update_now": "Update now",
        "update_later": "Later",
        "update_uptodate_title": "Up to date",
        "update_uptodate": "You have the latest version ({cur}).",
        "update_error_title": "Update check failed",
        "update_error": "Could not check for updates:\n{err}",
        "update_dl_title": "Updating",
        "update_dl_heading": "Updating to {ver}",
        "update_dl_starting": "Preparing download…",
        "update_dl_progress": "Downloading… {got} / {tot} MB",
        "update_dl_installing": "Installing… the app will restart automatically.",
        "update_dl_failed": "Update failed.",
    },
    "fr": {
        "app_title": "Transcription Vocale FR",
        "subtitle": "Transcription française haute précision, 100 % en local.",
        "theme": "Thème",
        "theme_dark": "Sombre",
        "theme_light": "Clair",
        "theme_halloween": "Halloween",
        "lang_button": "EN",
        "lang_button_tip": "Passer en anglais",
        "drop_title": "Glissez un fichier audio ici",
        "drop_sub": "ou cliquez pour parcourir  ·  MP3, WAV, M4A, MP4…",
        "no_file": "Aucun fichier sélectionné",
        "quality_max": "Qualité max (large-v3)",
        "quality_fast": "Rapide (medium)",
        "quality_tip": "large-v3 = meilleure précision. medium = plus rapide.",
        "transcribe": "Transcrire",
        "cancel": "Annuler",
        "section_text": "Texte transcrit",
        "copy": "Copier",
        "save": "Enregistrer",
        "placeholder": "Le texte transcrit s'affichera ici au fur et à mesure…",
        "ready": "Prêt.",
        "file_ready": "Fichier prêt. Cliquez sur « Transcrire ».",
        "initializing": "Initialisation…",
        "cancelling": "Annulation en cours…",
        "copied": "Texte copié dans le presse-papiers.",
        "saved": "Enregistré : {path}",
        "cancelled": "Transcription annulée.",
        "failed_status": "Échec de la transcription.",
        "loading_model": "Chargement du modèle «{model}» (compute={compute}, threads={threads})…",
        "downloading_model": "Premier lancement : téléchargement du modèle (~3 Go). Cela peut prendre plusieurs minutes.",
        "transcribing": "Transcription en cours…",
        "model_ready": "Modèle prêt en {sec:.1f}s.",
        "lang_info": "Langue : {lang} (prob. {prob:.2f}) — {dur:.1f}s",
        "done_status": "Terminé en {sec:.1f}s · {segs} segments · {dur:.1f}s d'audio ({ratio:.2f}× temps réel).",
        "browse_title": "Choisir un fichier audio/vidéo",
        "media_filter": "Fichiers média",
        "all_files": "Tous les fichiers",
        "save_title": "Enregistrer la transcription",
        "text_filter": "Fichier texte",
        "srt_filter": "Sous-titres",
        "error": "Erreur",
        "save_error": "Échec de l'enregistrement :\n{err}",
        "transcribe_error": "La transcription a échoué :\n\n{err}",
        "corrections": "Corrections",
        "corrections_tip": "Remplacements de mots personnalisés (ex. « Volio » → « Voelio »).",
        "corr_title": "Corrections de vocabulaire",
        "corr_intro": "Quand l'application comprend mal un mot, ajoutez une correction ici. "
                      "Elle est appliquée automatiquement à chaque transcription.",
        "corr_col_heard": "Compris (erroné)",
        "corr_col_fixed": "Remplacer par",
        "corr_add": "Ajouter",
        "corr_remove": "Supprimer",
        "corr_save": "Enregistrer",
        "corr_close": "Fermer",
        "corr_saved": "Corrections enregistrées.",
        "corr_placeholder_from": "ex. Volio",
        "corr_placeholder_to": "ex. Voelio",
        "corr_count": "{n} correction(s)",
        "diarize": "Identifier les interlocuteurs",
        "diarize_tip": "Détecte les tours de parole d'une conversation "
                       "(Interlocuteur 1, 2…). Heuristique légère basée sur les pauses.",
        "no_audio": "Ce fichier n'a pas de piste audio (vidéo seule ?). "
                    "Veuillez fournir un fichier contenant du son.",
        "update_check": "Vérifier les mises à jour",
        "update_checking": "Recherche de mises à jour…",
        "update_available_title": "Mise à jour disponible",
        "update_available": "Une nouvelle version est disponible : {new} "
                            "(vous avez {cur}).\n\nMettre à jour maintenant ? "
                            "L'application la télécharge et l'installe automatiquement.",
        "update_now": "Mettre à jour",
        "update_later": "Plus tard",
        "update_uptodate_title": "À jour",
        "update_uptodate": "Vous avez la dernière version ({cur}).",
        "update_error_title": "Échec de la vérification",
        "update_error": "Impossible de vérifier les mises à jour :\n{err}",
        "update_dl_title": "Mise à jour",
        "update_dl_heading": "Mise à jour vers {ver}",
        "update_dl_starting": "Préparation du téléchargement…",
        "update_dl_progress": "Téléchargement… {got} / {tot} Mo",
        "update_dl_installing": "Installation… l'application va redémarrer automatiquement.",
        "update_dl_failed": "Échec de la mise à jour.",
    },
}


# =========================================================================== #
#  THÈMES
# =========================================================================== #
@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    bg: str            # fond principal
    surface: str       # cartes / zones
    surface_alt: str   # zones secondaires
    border: str        # bordures
    border_focus: str  # bordure active / survol
    text: str          # texte principal
    text_dim: str      # texte secondaire
    text_faint: str    # texte discret
    accent: str        # couleur d'action
    accent_hover: str  # action survol
    accent_text: str   # texte sur accent
    danger: str        # couleur d'annulation


THEMES: dict[str, Theme] = {
    "dark": Theme(
        key="dark", label="Sombre",
        bg="#0f1420", surface="#161d2b", surface_alt="#141a26",
        border="#232d40", border_focus="#4c8dff",
        text="#e9edf5", text_dim="#aab2c2", text_faint="#7c869a",
        accent="#2b64d6", accent_hover="#3b74e6", accent_text="#ffffff",
        danger="#c85a5a",
    ),
    "light": Theme(
        key="light", label="Clair",
        bg="#f4f6fb", surface="#ffffff", surface_alt="#eef1f7",
        border="#d6dbe6", border_focus="#2b64d6",
        text="#1a2233", text_dim="#4a5468", text_faint="#8a93a6",
        accent="#2b64d6", accent_hover="#1f54c0", accent_text="#ffffff",
        danger="#c0392b",
    ),
    "halloween": Theme(
        key="halloween", label="Halloween",
        bg="#140d1c", surface="#1e1330", surface_alt="#180f26",
        border="#3a2352", border_focus="#ff7518",
        text="#f3e8ff", text_dim="#c9a8e6", text_faint="#8a6ea6",
        accent="#ff7518", accent_hover="#ff8f3d", accent_text="#140d1c",
        danger="#e0521f",
    ),
}


def build_qss(t: Theme) -> str:
    """Génère la feuille de style complète pour un thème donné."""
    return f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif; outline: none; }}

QMainWindow, QWidget#central {{ background-color: {t.bg}; }}
QWidget {{ color: {t.text}; }}

QLabel#header {{ font-size: 23px; font-weight: 700; color: {t.text}; }}
QLabel#subtitle {{ font-size: 13px; color: {t.text_faint}; }}
QLabel#sectionTitle {{ font-size: 14px; font-weight: 600; color: {t.text_dim}; }}
QLabel#status {{ font-size: 12px; color: {t.text_faint}; padding-top: 2px; }}

QFrame#dropZone {{
    background-color: {t.surface};
    border: 2px dashed {t.border};
    border-radius: 16px;
}}
QFrame#dropZone[hover="true"] {{
    background-color: {t.surface_alt};
    border: 2px dashed {t.border_focus};
}}
QLabel#dropIcon {{ font-size: 40px; color: {t.border_focus}; }}
QLabel#dropTitle {{ font-size: 17px; font-weight: 600; color: {t.text}; }}
QLabel#dropSub {{ font-size: 12px; color: {t.text_faint}; }}

QLabel#fileLabel {{
    font-size: 13px; color: {t.text_dim};
    padding: 9px 13px; background-color: {t.surface};
    border: 1px solid {t.border}; border-radius: 9px;
}}

QComboBox {{
    background-color: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 9px;
    padding: 8px 12px; min-width: 150px;
}}
QComboBox#themeCombo {{ min-width: 84px; }}
QComboBox:hover {{ border-color: {t.border_focus}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background-color: {t.surface}; color: {t.text};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    border: 1px solid {t.border}; border-radius: 8px;
    padding: 4px;
}}

QPushButton {{
    background-color: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 10px;
    padding: 11px 18px; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {t.border_focus}; }}
QPushButton:pressed {{ background-color: {t.surface_alt}; }}
QPushButton:disabled {{ color: {t.text_faint}; background-color: {t.surface_alt}; border-color: {t.border}; }}

QPushButton#primary {{
    background-color: {t.accent}; border: 1px solid {t.accent}; color: {t.accent_text};
    font-size: 14px; padding: 12px 20px;
}}
QPushButton#primary:hover {{ background-color: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton#primary:disabled {{ background-color: {t.surface_alt}; border-color: {t.border}; color: {t.text_faint}; }}

QPushButton#danger:hover {{ border-color: {t.danger}; color: {t.danger}; }}

QPushButton#langButton {{
    background-color: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 9px;
    padding: 8px 0; font-size: 13px; font-weight: 700;
}}
QPushButton#langButton:hover {{ border-color: {t.border_focus}; color: {t.border_focus}; }}

QLabel#versionLabel {{ color: {t.text_faint}; font-size: 12px; }}

QLabel#updIcon {{ font-size: 40px; color: {t.border_focus}; }}
QLabel#updTitle {{ font-size: 17px; font-weight: 700; color: {t.text}; }}
QLabel#updStatus {{ font-size: 13px; color: {t.text_dim}; }}
QProgressBar#updBar {{ background-color: {t.surface_alt}; border: none; border-radius: 4px; }}
QProgressBar#updBar::chunk {{ background-color: {t.accent}; border-radius: 4px; }}
QPushButton#updateButton {{
    background-color: transparent; color: {t.border_focus};
    border: none; padding: 0; font-size: 12px; font-weight: 600;
    text-align: left;
}}
QPushButton#updateButton:hover {{ color: {t.accent_hover}; text-decoration: underline; }}
QPushButton#updateButton:disabled {{ color: {t.text_faint}; }}

QProgressBar {{ background-color: {t.surface_alt}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background-color: {t.border_focus}; border-radius: 3px; }}

QPlainTextEdit#textView {{
    background-color: {t.surface_alt}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 12px;
    padding: 14px; font-size: 15px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {t.border}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.text_faint}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QMessageBox {{ background-color: {t.bg}; }}
QMessageBox QLabel {{ color: {t.text}; }}

QCheckBox#diarizeCheck {{
    color: {t.text_dim}; font-size: 13px; spacing: 8px; padding: 2px;
}}
QCheckBox#diarizeCheck::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {t.border}; background-color: {t.surface};
}}
QCheckBox#diarizeCheck::indicator:hover {{ border-color: {t.border_focus}; }}
QCheckBox#diarizeCheck::indicator:checked {{
    background-color: {t.accent}; border-color: {t.accent};
}}

QPushButton#corrButton {{
    background-color: {t.surface}; color: {t.text_dim};
    border: 1px solid {t.border}; border-radius: 9px;
    padding: 8px 14px; font-size: 13px; font-weight: 600;
}}
QPushButton#corrButton:hover {{ border-color: {t.border_focus}; color: {t.text}; }}
QPushButton#corrButton:disabled {{ color: {t.text_faint}; background-color: {t.surface_alt}; }}

QDialog {{ background-color: {t.bg}; }}

QTableWidget#corrTable {{
    background-color: {t.surface_alt}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 10px;
    gridline-color: {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QTableWidget#corrTable::item {{ padding: 6px 8px; }}
QHeaderView::section {{
    background-color: {t.surface}; color: {t.text_dim};
    padding: 8px; border: none; border-bottom: 1px solid {t.border};
    font-weight: 600;
}}
QTableWidget QLineEdit {{
    background-color: {t.surface}; color: {t.text};
    border: 1px solid {t.border_focus}; border-radius: 4px;
    selection-background-color: {t.accent};
}}
"""


# La transcription s'exécute dans un PROCESSUS séparé (QProcess), piloté
# directement par MainWindow. Cela permet un vrai « Annuler » instantané
# (kill du process), y compris pendant le téléchargement/chargement du modèle.


# =========================================================================== #
#  ZONE DE DÉPÔT
# =========================================================================== #
class DropZone(QFrame):
    fileDropped = Signal(str)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        self.icon = QLabel("🎙")
        self.icon.setObjectName("dropIcon")
        self.icon.setAlignment(Qt.AlignCenter)

        self.title = QLabel("Glissez un fichier audio ici")
        self.title.setObjectName("dropTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.sub = QLabel("ou cliquez pour parcourir  ·  MP3, WAV, M4A, MP4…")
        self.sub.setObjectName("dropSub")
        self.sub.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.sub)

    def set_enabled_visual(self, enabled: bool) -> None:
        self.setEnabled(enabled)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if is_media_file(url.toLocalFile()):
                    event.acceptProposedAction()
                    self._set_hover(True)
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_hover(False)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_hover(False)
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if is_media_file(local):
                self.fileDropped.emit(local)
                return

    def _set_hover(self, on: bool) -> None:
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)


# =========================================================================== #
#  FENÊTRE DES CORRECTIONS DE VOCABULAIRE
# =========================================================================== #
class CorrectionsDialog(QDialog):
    """Éditeur des corrections « mot entendu » -> « mot corrigé »,
    sauvegardées de façon persistante (survivent aux mises à jour)."""

    def __init__(self, parent, tr, qss: str) -> None:
        super().__init__(parent)
        self._tr = tr
        self.setModal(True)
        self.setMinimumSize(560, 460)
        self.setStyleSheet(qss)
        self.setWindowTitle(tr("corr_title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel(tr("corr_title"))
        title.setObjectName("header")
        root.addWidget(title)

        intro = QLabel(tr("corr_intro"))
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # Tableau : colonne 0 = entendu, colonne 1 = remplacement
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("corrTable")
        self.table.setHorizontalHeaderLabels([tr("corr_col_heard"), tr("corr_col_fixed")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        root.addWidget(self.table, stretch=1)

        # Boutons ligne : ajouter / supprimer
        row_btns = QHBoxLayout()
        row_btns.setSpacing(8)
        self.add_btn = QPushButton(tr("corr_add"))
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_row)
        self.remove_btn = QPushButton(tr("corr_remove"))
        self.remove_btn.setObjectName("danger")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(self._remove_row)
        row_btns.addWidget(self.add_btn)
        row_btns.addWidget(self.remove_btn)
        row_btns.addStretch(1)
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("status")
        row_btns.addWidget(self.count_lbl)
        root.addLayout(row_btns)

        # Boutons bas : enregistrer / fermer
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch(1)
        self.close_btn = QPushButton(tr("corr_close"))
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton(tr("corr_save"))
        self.save_btn.setObjectName("primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_and_close)
        bottom.addWidget(self.close_btn)
        bottom.addWidget(self.save_btn)
        root.addLayout(bottom)

        self._load_into_table()
        self.table.itemChanged.connect(lambda *_: self._update_count())
        self._update_count()

    # ---- Données ------------------------------------------------------ #
    def _load_into_table(self) -> None:
        corrections = load_corrections()
        self.table.setRowCount(0)
        for corr in corrections:
            self._append_row(corr.get("from", ""), corr.get("to", ""))

    def _append_row(self, src: str, dst: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(src))
        self.table.setItem(r, 1, QTableWidgetItem(dst))

    def _add_row(self) -> None:
        self._append_row("", "")
        r = self.table.rowCount() - 1
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))
        self._update_count()

    def _remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._update_count()

    def _update_count(self) -> None:
        n = 0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text().strip():
                n += 1
        self.count_lbl.setText(self._tr("corr_count", n=n))

    def _collect(self) -> list[dict]:
        out: list[dict] = []
        for r in range(self.table.rowCount()):
            src_item = self.table.item(r, 0)
            dst_item = self.table.item(r, 1)
            src = src_item.text().strip() if src_item else ""
            dst = dst_item.text() if dst_item else ""
            if src:
                out.append({
                    "from": src, "to": dst,
                    "whole_word": True, "case_sensitive": False,
                })
        return out

    def _save_and_close(self) -> None:
        save_corrections(self._collect())
        self.accept()


# =========================================================================== #
#  VÉRIFICATION DES MISES À JOUR (en arrière-plan)
# =========================================================================== #
def _parse_version(v: str) -> tuple:
    """Convertit 'v1.4.0' ou '1.4.0' en tuple comparable (1, 4, 0)."""
    v = v.strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)


class UpdateChecker(QObject):
    """Interroge l'API GitHub Releases dans un thread séparé (non bloquant).

    Émet le tag de version ET l'URL de l'installeur (.exe) trouvé dans les
    assets de la release, pour permettre une mise à jour automatique.
    """

    # (tag, installer_url)
    result = Signal(str, str)
    failed = Signal(str)
    done = Signal()

    def run(self) -> None:
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                RELEASES_API,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "TranscriptionVocaleFR"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            tag = str(data.get("tag_name", "")).strip()

            # Cherche l'asset installeur (…Setup….exe) parmi les fichiers.
            installer_url = ""
            for asset in data.get("assets", []):
                name = str(asset.get("name", "")).lower()
                if name.endswith(".exe") and "setup" in name:
                    installer_url = str(asset.get("browser_download_url", ""))
                    break
            self.result.emit(tag, installer_url)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class UpdateDownloader(QObject):
    """Télécharge l'installeur avec progression, dans un thread séparé."""

    progress = Signal(int, int)   # octets reçus, total
    finished = Signal(str)        # chemin du fichier téléchargé
    failed = Signal(str)
    done = Signal()

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            import tempfile
            import urllib.request

            req = urllib.request.Request(
                self._url, headers={"User-Agent": "TranscriptionVocaleFR"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0) or 0)
                # Fichier temporaire .exe (conservé après fermeture).
                fd, tmp_path = tempfile.mkstemp(suffix="_TranscriptionVocaleFR-Setup.exe")
                received = 0
                with os.fdopen(fd, "wb") as out:
                    while True:
                        if self._cancel:
                            raise RuntimeError("cancelled")
                        chunk = resp.read(262144)  # 256 Ko
                        if not chunk:
                            break
                        out.write(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
            self.finished.emit(tmp_path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class UpdateDialog(QDialog):
    """Jolie fenêtre de mise à jour : progression du téléchargement puis
    lancement silencieux de l'installeur. L'utilisateur n'a rien à faire."""

    def __init__(self, parent, tr, qss: str, new_tag: str, installer_url: str) -> None:
        super().__init__(parent)
        self._tr = tr
        self._url = installer_url
        self._new_tag = new_tag
        self._thread: QThread | None = None
        self._worker: UpdateDownloader | None = None
        self._installer_path: str | None = None

        self.setModal(True)
        self.setFixedSize(440, 240)
        self.setStyleSheet(qss)
        self.setWindowTitle(tr("update_dl_title"))
        # Empêche la fermeture pendant le travail (pas de bouton close actif).
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignTop)

        icon = QLabel("⬇")
        icon.setObjectName("updIcon")
        icon.setAlignment(Qt.AlignCenter)
        root.addWidget(icon)

        self.title = QLabel(tr("update_dl_heading", ver=new_tag))
        self.title.setObjectName("updTitle")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        self.bar = QProgressBar()
        self.bar.setObjectName("updBar")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        root.addWidget(self.bar)

        self.status = QLabel(tr("update_dl_starting"))
        self.status.setObjectName("updStatus")
        self.status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status)

    def start(self) -> None:
        """Démarre le téléchargement dès l'ouverture."""
        thread = QThread(self)
        worker = UpdateDownloader(self._url)
        worker.moveToThread(thread)
        self._thread = thread
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_downloaded)
        worker.failed.connect(self._on_failed)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_progress(self, received: int, total: int) -> None:
        if total > 0:
            pct = int(received * 100 / total)
            self.bar.setRange(0, 100)
            self.bar.setValue(pct)
            mb_r = received / (1024 * 1024)
            mb_t = total / (1024 * 1024)
            self.status.setText(
                self._tr("update_dl_progress", got=f"{mb_r:.0f}", tot=f"{mb_t:.0f}"))
        else:
            self.bar.setRange(0, 0)  # indéterminé
            self.status.setText(self._tr("update_dl_starting"))

    def _on_downloaded(self, path: str) -> None:
        self._installer_path = path
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.status.setText(self._tr("update_dl_installing"))
        # Lance l'installeur en silencieux puis ferme l'app.
        QTimer.singleShot(600, self._launch_installer)

    def _launch_installer(self) -> None:
        if not self._installer_path:
            self._on_failed("installateur introuvable")
            return
        try:
            # /SILENT : installation automatique avec petite barre de progression
            # native de l'installeur ; /CLOSEAPPLICATIONS pour remplacer les
            # fichiers ; on ferme l'app pour libérer les fichiers.
            import subprocess
            subprocess.Popen(
                [self._installer_path, "/SILENT", "/CLOSEAPPLICATIONS",
                 "/RESTARTAPPLICATIONS", "/NORESTART"],
                close_fds=True,
            )
            # Ferme l'application : l'installeur prend le relais.
            QTimer.singleShot(300, self._quit_app)
        except Exception as exc:  # noqa: BLE001
            self._on_failed(str(exc))

    def _quit_app(self) -> None:
        self.accept()
        QApplication.instance().quit()

    def _on_failed(self, err: str) -> None:
        self.setWindowFlag(Qt.WindowCloseButtonHint, True)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status.setText(self._tr("update_dl_failed"))
        QMessageBox.warning(self, self._tr("update_error_title"),
                            self._tr("update_error", err=err))
        self.reject()


# =========================================================================== #
#  FENÊTRE PRINCIPALE
# =========================================================================== #
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(780, 640)

        self._settings = QSettings("Trustia", APP_NAME)
        self._process: QProcess | None = None
        self._cancelled_by_user = False
        self._stdout_buffer = ""
        self._current_file: str | None = None
        self._result: dict | None = None
        self._live_parts: list[str] = []
        self._last_status_key: tuple[str, dict] | None = None
        self._update_thread: QThread | None = None
        self._update_worker: UpdateChecker | None = None

        # Langue : anglais par défaut.
        lang = self._settings.value("lang", "en")
        self._lang = lang if lang in STRINGS else "en"

        theme_key = self._settings.value("theme", "dark")
        if theme_key not in THEMES:
            theme_key = "dark"
        self._theme = THEMES[theme_key]

        self._build_ui()
        self._apply_theme(self._theme)
        self._retranslate()

    # ---- Traduction --------------------------------------------------- #
    def tr(self, key: str, **kwargs) -> str:  # noqa: A003
        template = STRINGS.get(self._lang, STRINGS["en"]).get(key, key)
        return template.format(**kwargs) if kwargs else template

    def _set_status(self, key: str, **kwargs) -> None:
        """Mémorise la clé pour re-traduire si la langue change."""
        self._last_status_key = (key, kwargs)
        self.status.setText(self.tr(key, **kwargs))

    def _toggle_language(self) -> None:
        self._lang = "fr" if self._lang == "en" else "en"
        self._settings.setValue("lang", self._lang)
        self._retranslate()

    # ---- Interface ---------------------------------------------------- #
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(16)

        # En-tête + bouton langue + sélecteur de thème
        top = QHBoxLayout()
        top.setSpacing(12)
        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        self.header = QLabel(APP_NAME)
        self.header.setObjectName("header")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("subtitle")
        head_col.addWidget(self.header)
        head_col.addWidget(self.subtitle)

        # Ligne version + bouton « Vérifier les mises à jour »
        ver_row = QHBoxLayout()
        ver_row.setSpacing(10)
        self.version_lbl = QLabel(f"v{__version__}")
        self.version_lbl.setObjectName("versionLabel")
        self.update_btn = QPushButton("")
        self.update_btn.setObjectName("updateButton")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self._check_updates)
        ver_row.addWidget(self.version_lbl)
        ver_row.addWidget(self.update_btn)
        ver_row.addStretch(1)
        head_col.addLayout(ver_row)

        top.addLayout(head_col, stretch=1)

        # Colonne thème (label au-dessus, combo en dessous)
        theme_col = QVBoxLayout()
        theme_col.setSpacing(2)
        self.theme_lbl = QLabel("")
        self.theme_lbl.setObjectName("subtitle")
        self.theme_lbl.setAlignment(Qt.AlignRight)
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themeCombo")
        # S'adapte au libellé courant : compact, sans jamais couper le texte.
        self.theme_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for key in THEMES:
            self.theme_combo.addItem("", key)  # libellés remplis par _retranslate
        idx = self.theme_combo.findData(self._theme.key)
        self.theme_combo.setCurrentIndex(max(0, idx))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_col.addWidget(self.theme_lbl)
        theme_col.addWidget(self.theme_combo)

        # Bouton de bascule de langue, aligné sur le combo de thème (même ligne)
        self.lang_btn = QPushButton("FR")
        self.lang_btn.setObjectName("langButton")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.setFixedWidth(46)
        self.lang_btn.clicked.connect(self._toggle_language)

        lang_col = QVBoxLayout()
        lang_col.setSpacing(2)
        lang_spacer = QLabel("")          # espace fantôme = hauteur du label thème
        lang_spacer.setObjectName("subtitle")
        lang_col.addWidget(lang_spacer)
        lang_col.addWidget(self.lang_btn)

        top.addLayout(lang_col)
        top.addLayout(theme_col)
        root.addLayout(top)

        # Zone de dépôt
        self.drop = DropZone()
        self.drop.fileDropped.connect(self._on_file_selected)
        self.drop.clicked.connect(self._browse)
        root.addWidget(self.drop)

        # Ligne fichier + qualité
        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_label = QLabel("")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        file_row.addWidget(self.file_label, stretch=1)

        self.corrections_btn = QPushButton("")
        self.corrections_btn.setObjectName("corrButton")
        self.corrections_btn.setCursor(Qt.PointingHandCursor)
        self.corrections_btn.clicked.connect(self._open_corrections)
        file_row.addWidget(self.corrections_btn)

        self.quality_combo = QComboBox()
        self.quality_combo.addItem("", "large-v3")   # libellés via _retranslate
        self.quality_combo.addItem("", "medium")
        file_row.addWidget(self.quality_combo)
        root.addLayout(file_row)

        # Option : identifier les interlocuteurs (diarisation légère)
        opt_row = QHBoxLayout()
        self.diarize_check = QCheckBox("")
        self.diarize_check.setObjectName("diarizeCheck")
        self.diarize_check.setCursor(Qt.PointingHandCursor)
        opt_row.addWidget(self.diarize_check)
        opt_row.addStretch(1)
        root.addLayout(opt_row)

        # Boutons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.transcribe_btn = QPushButton("")
        self.transcribe_btn.setObjectName("primary")
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.setCursor(Qt.PointingHandCursor)
        self.transcribe_btn.clicked.connect(self._start)

        self.cancel_btn = QPushButton("")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel)

        action_row.addWidget(self.transcribe_btn, stretch=2)
        action_row.addWidget(self.cancel_btn, stretch=1)
        root.addLayout(action_row)

        # Progression
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # En-tête section texte
        text_header = QHBoxLayout()
        self.text_title = QLabel("")
        self.text_title.setObjectName("sectionTitle")
        text_header.addWidget(self.text_title)
        text_header.addStretch(1)
        self.copy_btn = QPushButton("")
        self.copy_btn.setEnabled(False)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = QPushButton("")
        self.save_btn.setEnabled(False)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)
        text_header.addWidget(self.copy_btn)
        text_header.addWidget(self.save_btn)
        root.addLayout(text_header)

        # Zone de texte
        self.text_view = QPlainTextEdit()
        self.text_view.setObjectName("textView")
        root.addWidget(self.text_view, stretch=1)

        # Statut
        self.status = QLabel("")
        self.status.setObjectName("status")
        root.addWidget(self.status)

    # ---- Re-traduction de toute l'interface --------------------------- #
    def _retranslate(self) -> None:
        self.setWindowTitle(self.tr("app_title"))
        self.header.setText(self.tr("app_title"))
        self.subtitle.setText(self.tr("subtitle"))
        self.lang_btn.setText(self.tr("lang_button"))
        self.lang_btn.setToolTip(self.tr("lang_button_tip"))
        self.update_btn.setText(self.tr("update_check"))
        self.theme_lbl.setText(self.tr("theme"))

        # Libellés des thèmes (sans changer la sélection courante)
        theme_labels = {
            "dark": self.tr("theme_dark"),
            "light": self.tr("theme_light"),
            "halloween": self.tr("theme_halloween"),
        }
        for i in range(self.theme_combo.count()):
            key = self.theme_combo.itemData(i)
            self.theme_combo.setItemText(i, theme_labels.get(key, key))

        # Zone de dépôt
        self.drop.title.setText(self.tr("drop_title"))
        self.drop.sub.setText(self.tr("drop_sub"))

        # Fichier / qualité
        if self._current_file:
            self.file_label.setText(Path(self._current_file).name)
        else:
            self.file_label.setText(self.tr("no_file"))
        self.quality_combo.setItemText(0, self.tr("quality_max"))
        self.quality_combo.setItemText(1, self.tr("quality_fast"))
        self.quality_combo.setToolTip(self.tr("quality_tip"))
        self.corrections_btn.setText(self.tr("corrections"))
        self.corrections_btn.setToolTip(self.tr("corrections_tip"))
        self.diarize_check.setText(self.tr("diarize"))
        self.diarize_check.setToolTip(self.tr("diarize_tip"))

        # Boutons
        self.transcribe_btn.setText(self.tr("transcribe"))
        self.cancel_btn.setText(self.tr("cancel"))
        self.text_title.setText(self.tr("section_text"))
        self.copy_btn.setText(self.tr("copy"))
        self.save_btn.setText(self.tr("save"))
        self.text_view.setPlaceholderText(self.tr("placeholder"))

        # Statut : re-traduit le dernier message si possible
        if self._last_status_key is not None:
            key, kwargs = self._last_status_key
            self.status.setText(self.tr(key, **kwargs))
        else:
            self._set_status("ready")

    # ---- Thèmes ------------------------------------------------------- #
    def _apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_qss(theme))
        self.setWindowIcon(app_icon())

    def _on_theme_changed(self, _index: int) -> None:
        key = self.theme_combo.currentData()
        if key in THEMES:
            self._apply_theme(THEMES[key])
            self._settings.setValue("theme", key)

    # ---- Sélection de fichier ---------------------------------------- #
    def _browse(self) -> None:
        if self._process is not None:
            return
        patterns = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("browse_title"), "",
            f"{self.tr('media_filter')} ({patterns});;{self.tr('all_files')} (*.*)",
        )
        if path:
            self._on_file_selected(path)

    def _on_file_selected(self, path: str) -> None:
        self._current_file = path
        self.file_label.setText(Path(path).name)
        self.transcribe_btn.setEnabled(True)
        self._set_status("file_ready")

    def _open_corrections(self) -> None:
        dialog = CorrectionsDialog(self, self.tr, build_qss(self._theme))
        if dialog.exec() == QDialog.Accepted:
            self._set_status("corr_saved")

    # ---- Vérification des mises à jour -------------------------------- #
    def _check_updates(self) -> None:
        if self._update_thread is not None:
            return  # déjà en cours
        self.update_btn.setEnabled(False)
        self._set_status("update_checking")

        thread = QThread(self)
        worker = UpdateChecker()
        worker.moveToThread(thread)
        self._update_thread = thread
        self._update_worker = worker

        worker.result.connect(self._on_update_result)
        worker.failed.connect(self._on_update_failed)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_update_thread_done)
        thread.start()

    def _on_update_result(self, tag: str, installer_url: str) -> None:
        if not tag:
            self._on_update_failed("réponse vide")
            return
        latest = _parse_version(tag)
        current = _parse_version(__version__)
        if latest > current:
            box = QMessageBox(self)
            box.setWindowTitle(self.tr("update_available_title"))
            box.setText(self.tr("update_available", new=tag, cur=f"v{__version__}"))
            box.setIcon(QMessageBox.Question)
            yes_btn = box.addButton(self.tr("update_now"), QMessageBox.AcceptRole)
            box.addButton(self.tr("update_later"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is yes_btn:
                if installer_url:
                    # Mise à jour automatique : jolie fenêtre + installeur silencieux.
                    dlg = UpdateDialog(self, self.tr, build_qss(self._theme),
                                       tag, installer_url)
                    dlg.start()
                    dlg.exec()
                else:
                    # Pas d'installeur trouvé : ouvre la page (repli).
                    QDesktopServices.openUrl(QUrl(RELEASES_PAGE))
            self._set_status("ready")
        else:
            QMessageBox.information(
                self, self.tr("update_uptodate_title"),
                self.tr("update_uptodate", cur=f"v{__version__}"),
            )
            self._set_status("ready")

    def _on_update_failed(self, err: str) -> None:
        QMessageBox.warning(
            self, self.tr("update_error_title"),
            self.tr("update_error", err=err),
        )
        self._set_status("ready")

    def _on_update_thread_done(self) -> None:
        self.update_btn.setEnabled(True)
        self._update_thread = None
        self._update_worker = None

    # ---- Transcription (processus séparé, annulable par kill) --------- #
    def _worker_command(self) -> tuple[str, list[str]]:
        """Retourne (programme, arguments) pour lancer le worker.
        Fonctionne en mode script (python) comme en mode exe figé."""
        model = self.quality_combo.currentData()
        diarize = "1" if self.diarize_check.isChecked() else "0"
        args_tail = [self._current_file, model, "fr", "int8", "8", diarize]
        if getattr(sys, "frozen", False):
            # Dans l'exe : on relance l'exe lui-même avec un drapeau spécial.
            return sys.executable, ["--run-worker", *args_tail]
        worker_script = str(APP_ROOT / "transcribe_worker.py")
        return sys.executable, [worker_script, *args_tail]

    def _start(self) -> None:
        if not self._current_file or self._process is not None:
            return
        self._result = None
        self._live_parts = []
        self._stdout_buffer = ""
        self._cancelled_by_user = False
        self.text_view.clear()
        self._set_busy(True)
        self._set_status("initializing")

        program, arguments = self._worker_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(arguments)
        proc.setWorkingDirectory(str(APP_ROOT))
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_proc_stdout)
        proc.finished.connect(self._on_proc_finished)
        proc.errorOccurred.connect(self._on_proc_error)
        self._process = proc
        proc.start()

    def _cancel(self) -> None:
        if self._process is not None:
            self._cancelled_by_user = True
            self._set_status("cancelling")
            self.cancel_btn.setEnabled(False)
            # Kill immédiat : interrompt téléchargement / chargement / transcription.
            self._process.kill()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text_view.toPlainText())
        self._set_status("copied")

    def _save(self) -> None:
        default = "transcription.txt"
        if self._current_file:
            default = str(Path(self._current_file).with_suffix(".txt"))
        path, selected = QFileDialog.getSaveFileName(
            self, self.tr("save_title"), default,
            f"{self.tr('text_filter')} (*.txt);;{self.tr('srt_filter')} (*.srt)",
        )
        if not path:
            return
        try:
            srt = self._result.get("srt") if self._result else None
            if path.lower().endswith(".srt") and srt:
                Path(path).write_text(srt, encoding="utf-8")
            else:
                Path(path).write_text(
                    self.text_view.toPlainText().strip() + "\n", encoding="utf-8"
                )
            self._set_status("saved", path=path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("error"),
                                 self.tr("save_error", err=str(exc)))

    # ---- Lecture des événements JSON du processus --------------------- #
    def _on_proc_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        self._stdout_buffer += data
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()
            if line:
                self._handle_event(line)

    def _handle_event(self, line: str) -> None:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            return  # ligne non-JSON (log parasite) : ignorée
        etype = evt.get("type")

        if etype == "phase":
            params = evt.get("params") or {}
            self._set_status(evt.get("key", ""), **params)

        elif etype == "segment":
            self._live_parts.append(evt.get("text", ""))
            self.text_view.setPlainText(" ".join(self._live_parts).strip())
            sb = self.text_view.verticalScrollBar()
            sb.setValue(sb.maximum())

        elif etype == "finished":
            self._result = evt
            self.text_view.setPlainText(evt.get("text", ""))
            elapsed = evt.get("elapsed", 0.0) or 0.0
            duration = evt.get("duration", 0.0) or 0.0
            ratio = (duration / elapsed) if elapsed else 0.0
            self._set_status("done_status", sec=elapsed,
                             segs=evt.get("segments", 0), dur=duration, ratio=ratio)
            has_text = bool(evt.get("text"))
            self.copy_btn.setEnabled(has_text)
            self.save_btn.setEnabled(has_text)

        elif etype == "failed":
            self._set_status("failed_status")
            raw = evt.get("message", "")
            # Message clair pour un fichier sans piste audio (ex. MP4 vidéo seule).
            msg = self.tr("no_audio") if raw == "no_audio_track" else \
                self.tr("transcribe_error", err=raw)
            QMessageBox.critical(self, self.tr("error"), msg)

    def _on_proc_error(self, _error) -> None:
        # Une erreur de process (ex. « crashed ») après un kill volontaire est
        # normale : elle sera traitée dans _on_proc_finished.
        pass

    def _on_proc_finished(self, _code: int, _status) -> None:
        """Fin du processus : nettoie l'UI. Distingue annulation / fin normale."""
        if self._cancelled_by_user:
            self._set_status("cancelled")
        self._set_busy(False)
        proc = self._process
        self._process = None
        if proc is not None:
            proc.deleteLater()

    # ---- État occupé -------------------------------------------------- #
    def _set_busy(self, busy: bool) -> None:
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        self.transcribe_btn.setEnabled(not busy and self._current_file is not None)
        self.cancel_btn.setEnabled(busy)
        self.drop.set_enabled_visual(not busy)
        self.quality_combo.setEnabled(not busy)
        self.corrections_btn.setEnabled(not busy)
        self.diarize_check.setEnabled(not busy)
        self.theme_combo.setEnabled(True)  # thème toujours changeable
        if busy:
            self.copy_btn.setEnabled(False)
            self.save_btn.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._process is not None:
            self._cancelled_by_user = True
            self._process.kill()
            self._process.waitForFinished(3000)
        event.accept()


# =========================================================================== #
#  ICÔNE
# =========================================================================== #
def _asset_path(name: str) -> Path | None:
    """Localise un fichier d'asset en mode script comme en mode exe."""
    from transcriber_core import RESOURCE_ROOT, APP_ROOT
    for root in (RESOURCE_ROOT, APP_ROOT):
        candidate = root / "assets" / name
        if candidate.exists():
            return candidate
    return None


_ICON_CACHE: QIcon | None = None


def app_icon() -> QIcon:
    """Icône de l'application : charge assets/icon.ico|svg, sinon dessine un repli."""
    global _ICON_CACHE
    if _ICON_CACHE is not None:
        return _ICON_CACHE

    for name in ("icon.ico", "icon.png", "icon.svg"):
        path = _asset_path(name)
        if path is not None:
            icon = QIcon(str(path))
            if not icon.isNull():
                _ICON_CACHE = icon
                return icon

    # Repli : micro dessiné programmatiquement (jamais utilisé si les assets sont là).
    size = 64
    pix = QPixmap(size, size)
    pix.fill(QColor("#0f1420"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#2b64d6"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(size // 2 - 9, 12, 18, 28, 9, 9)
    pen = QPen(QColor("#2b64d6"))
    pen.setWidth(3)
    p.setPen(pen)
    p.drawArc(size // 2 - 15, 20, 30, 30, 200 * 16, 140 * 16)
    p.drawLine(size // 2, 50, size // 2, 56)
    p.end()
    _ICON_CACHE = QIcon(pix)
    return _ICON_CACHE


def _run_worker_mode() -> int:
    """Mode « worker » : utilisé quand l'exe figé se relance lui-même pour
    exécuter la transcription dans un processus séparé (annulable par kill)."""
    from transcribe_worker import main as worker_main
    # Retire le drapeau pour retrouver les arguments attendus par le worker.
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    return worker_main()


def main() -> int:
    # Point d'entrée « worker » (exe figé qui se relance pour transcrire).
    if len(sys.argv) > 1 and sys.argv[1] == "--run-worker":
        return _run_worker_mode()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
