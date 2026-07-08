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

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSettings
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QFileDialog, QFrame, QProgressBar,
    QMessageBox, QComboBox, QSizePolicy,
)

from transcriber_core import (
    Transcriber, TranscriptionOptions, TranscriptionResult, Segment,
    TranscriptionCancelled, is_media_file, MEDIA_EXTS,
)


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
"""


# =========================================================================== #
#  WORKER (thread de transcription)
# =========================================================================== #
class TranscriptionWorker(QObject):
    """Exécute la transcription dans un thread. N'émet QUE des données pures
    (str / dataclasses) — jamais de manipulation de widgets ici."""

    # phase émet (clé_de_traduction, dict_de_parametres) => la GUI traduit.
    phase = Signal(str, object)
    segment = Signal(object)          # Segment
    finished = Signal(object)         # TranscriptionResult
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()                   # toujours émis en dernier (nettoyage)

    def __init__(self, transcriber: Transcriber, path: str,
                 options: TranscriptionOptions) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._path = path
        self._options = options
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _log_adapter(self, message: str) -> None:
        """Ignore le texte brut du core ; les phases sont émises séparément."""
        # Volontairement vide : l'affichage passe par les signaux `phase`
        # pour rester traduisible. On garde l'adaptateur pour compat API.

    def run(self) -> None:
        try:
            import os
            threads = self._options.cpu_threads or (os.cpu_count() or 4)
            self.phase.emit("loading_model", {
                "model": self._options.model_name,
                "compute": self._options.compute_type,
                "threads": threads,
            })
            self.phase.emit("downloading_model", {})
            self._transcriber.load(self._options, log=self._log_adapter)

            result = self._transcriber.transcribe(
                self._path,
                self._options,
                log=self._log_adapter,
                on_segment=self.segment.emit,
                cancel=lambda: self._cancel,
            )
            self.finished.emit(result)
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


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
#  FENÊTRE PRINCIPALE
# =========================================================================== #
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(780, 640)

        self._settings = QSettings("Trustia", APP_NAME)
        self._transcriber = Transcriber()
        self._thread: QThread | None = None
        self._worker: TranscriptionWorker | None = None
        self._current_file: str | None = None
        self._result: TranscriptionResult | None = None
        self._live_parts: list[str] = []
        self._last_status_key: tuple[str, dict] | None = None

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
        top.addLayout(head_col, stretch=1)

        # Bouton de bascule de langue
        self.lang_btn = QPushButton("FR")
        self.lang_btn.setObjectName("langButton")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.setFixedWidth(52)
        self.lang_btn.clicked.connect(self._toggle_language)
        top.addWidget(self.lang_btn, alignment=Qt.AlignTop)

        theme_col = QVBoxLayout()
        theme_col.setSpacing(2)
        self.theme_lbl = QLabel("")
        self.theme_lbl.setObjectName("subtitle")
        self.theme_lbl.setAlignment(Qt.AlignRight)
        self.theme_combo = QComboBox()
        for key in THEMES:
            self.theme_combo.addItem("", key)  # libellés remplis par _retranslate
        idx = self.theme_combo.findData(self._theme.key)
        self.theme_combo.setCurrentIndex(max(0, idx))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_col.addWidget(self.theme_lbl)
        theme_col.addWidget(self.theme_combo)
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

        self.quality_combo = QComboBox()
        self.quality_combo.addItem("", "large-v3")   # libellés via _retranslate
        self.quality_combo.addItem("", "medium")
        file_row.addWidget(self.quality_combo)
        root.addLayout(file_row)

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
        if self._worker is not None:
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

    # ---- Transcription ------------------------------------------------ #
    def _start(self) -> None:
        if not self._current_file or self._worker is not None:
            return
        self._result = None
        self._live_parts = []
        self.text_view.clear()
        self._set_busy(True)
        self._set_status("initializing")

        options = TranscriptionOptions(
            model_name=self.quality_combo.currentData(),
            language="fr",
            compute_type="int8",
            beam_size=8,
        )

        thread = QThread(self)
        worker = TranscriptionWorker(self._transcriber, self._current_file, options)
        worker.moveToThread(thread)
        self._thread = thread
        self._worker = worker

        # Résultats (slots exécutés dans le thread principal via QueuedConnection).
        worker.phase.connect(self._on_phase)
        worker.segment.connect(self._on_segment)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)

        # Cycle de vie du thread — pattern Qt canonique, sans wait() dans un slot.
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)          # arrête la boucle du thread
        worker.done.connect(worker.deleteLater)   # planifie la destruction du worker
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)  # nettoyage UI (thread principal)

        thread.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._set_status("cancelling")
            self.cancel_btn.setEnabled(False)

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
            if path.lower().endswith(".srt") and self._result and self._result.srt:
                Path(path).write_text(self._result.srt, encoding="utf-8")
            else:
                Path(path).write_text(
                    self.text_view.toPlainText().strip() + "\n", encoding="utf-8"
                )
            self._set_status("saved", path=path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("error"),
                                 self.tr("save_error", err=str(exc)))

    # ---- Réactions du worker (thread principal) ----------------------- #
    def _on_phase(self, key: str, params: object) -> None:
        params = params if isinstance(params, dict) else {}
        self._set_status(key, **params)

    def _on_segment(self, segment: Segment) -> None:
        self._live_parts.append(segment.text)
        self.text_view.setPlainText(" ".join(self._live_parts).strip())
        sb = self.text_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, result: TranscriptionResult) -> None:
        self._result = result
        self.text_view.setPlainText(result.text)
        ratio = (result.duration / result.elapsed) if result.elapsed else 0.0
        self._set_status("done_status", sec=result.elapsed,
                         segs=len(result.segments), dur=result.duration, ratio=ratio)
        self.copy_btn.setEnabled(bool(result.text))
        self.save_btn.setEnabled(bool(result.text))

    def _on_failed(self, message: str) -> None:
        self._set_status("failed_status")
        QMessageBox.critical(self, self.tr("error"),
                             self.tr("transcribe_error", err=message))

    def _on_cancelled(self) -> None:
        self._set_status("cancelled")

    def _on_thread_finished(self) -> None:
        """Nettoyage UI une fois le thread réellement terminé.
        S'exécute dans le thread principal (signal QThread.finished).
        N'appelle jamais wait() ici : le thread s'est déjà arrêté seul."""
        self._set_busy(False)
        self._thread = None
        self._worker = None

    # ---- État occupé -------------------------------------------------- #
    def _set_busy(self, busy: bool) -> None:
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        self.transcribe_btn.setEnabled(not busy and self._current_file is not None)
        self.cancel_btn.setEnabled(busy)
        self.drop.set_enabled_visual(not busy)
        self.quality_combo.setEnabled(not busy)
        self.theme_combo.setEnabled(True)  # thème toujours changeable
        if busy:
            self.copy_btn.setEnabled(False)
            self.save_btn.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker:
            self._worker.cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
