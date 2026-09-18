<div align="center">

<img src="assets/icon.svg" alt="French Voice Transcription" width="128" height="128" />

# French Voice Transcription

**Turn your French speech into text — high accuracy, 100% on your machine.**

A simple, modern desktop app powered by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and OpenAI Whisper's
`large-v3` model. Your audio files never leave your computer.

<br/>

**🌍 Language:** **English** · [Français](#-français)

<br/>

[![Build & Release](https://img.shields.io/github/actions/workflow/status/Adrien10200/transcription-vocale-fr/build-release.yml?style=for-the-badge&logo=github&label=Build)](https://github.com/Adrien10200/transcription-vocale-fr/actions/workflows/build-release.yml)
[![Release](https://img.shields.io/github/v/release/Adrien10200/transcription-vocale-fr?style=for-the-badge&logo=github&color=2b64d6&label=Release)](https://github.com/Adrien10200/transcription-vocale-fr/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Adrien10200/transcription-vocale-fr/total?style=for-the-badge&logo=github&color=success&label=Downloads)](https://github.com/Adrien10200/transcription-vocale-fr/releases)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Whisper](https://img.shields.io/badge/Engine-faster--whisper-ff6f61?style=flat-square)](https://github.com/SYSTRAN/faster-whisper)
[![Platform](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white)](#)
[![License](https://img.shields.io/github/license/Adrien10200/transcription-vocale-fr?style=flat-square&color=blue&label=License)](LICENSE)
[![Built with AI](https://img.shields.io/badge/Built%20with-AI-8A2BE2?style=flat-square&logo=openai&logoColor=white)](#)

</div>

---

## ✨ Features

- 🎯 **High French accuracy** — `large-v3` model, beam search, temperature fallback, voice-activity detection (VAD).
- 🖱 **Drag & drop** an audio/video file, or click to browse.
- 🎙 **Record from your microphone or desktop sound** — *Record* (record then transcribe) or *Live* (text appears while you speak); capture your mic **or system audio** (WASAPI loopback) via the device selector.
- 🔒 **100% offline** — no data ever leaves your machine.
- ⚡ **Fluid interface** — transcription runs in the background, text streams in live, and everything is **cancellable**.
- 📋 **Copy / Save** the result in one click (`.txt` or `.srt` subtitles).
- 📝 **Custom corrections** — teach the app your vocabulary (e.g. `Volio` → `Voelio`); replacements are applied automatically and **persist across upgrades**.
- 🗣 **Speaker identification** — optional lightweight diarization tags turn-taking (`Interlocuteur 1 / 2…`) in conversations, fully offline.
- 📦 **Installer** — one-click setup; the model cache is stored **outside** the app folder, so updates never re-download the ~3 GB model.
- 🎨 **3 themes** — 🌙 Dark · ☀️ Light · 🎃 Halloween.
- 🌍 **Bilingual UI** — switch between English and French with one click.
- 🎬 **Many formats** — MP3, WAV, M4A, FLAC, OGG, MP4, MKV, MOV… (audio decoding built in via PyAV, no external ffmpeg).
- 🪶 **Lightweight** — ~270 MB app (down from 750 MB), plus the model cache.

---

## 🚀 Installation (end user)

1. Open the [**Releases**](https://github.com/Adrien10200/transcription-vocale-fr/releases/latest) tab.
2. Download `Transcription-Vocale-FR-…-win64.zip`.
3. Unzip it anywhere.
4. Double-click **`Transcription Vocale FR.exe`**.

> 💡 **First launch:** the `large-v3` model (~3 GB) is downloaded automatically and
> cached in `%LOCALAPPDATA%\TranscriptionVocaleFR\models`. Subsequent launches
> are instant, and **upgrading the app never re-downloads the model** — the cache
> lives outside the app folder.

### ⚠️ Windows SmartScreen warning

The app is signed with a **self-signed certificate**, so Windows shows a blue
**“Windows protected your PC”** screen the first time, and SmartScreen displays
**Publisher: Unknown**. This is normal: a self-signed certificate is not issued
by a trusted certificate authority, so Windows cannot verify the publisher.
Removing this would require a paid OV/EV code-signing certificate. To run the app:

1. Click **More info**.
2. Click **Run anyway**.

The app is open-source — you can review every line here. Once installed, use the
**Check for updates** button inside the app: it downloads and installs new
versions automatically (no manual download).

---

## 🖥 Usage

| Step | Action |
|:----:|--------|
| **1** | **Drag** your audio file onto the drop zone (or click to browse). |
| **2** | Pick the quality — default is **Best quality (large-v3)**. |
| **3** | Click **Transcribe**. Text streams in live. |
| **4** | **Copy** or **Save** the result when done. |

Theme (Dark / Light / Halloween) and language (EN / FR) can be changed at any time
from the top-right corner.

---

## 🧠 Why it's accurate

The app is tuned for **maximum quality**, not speed:

| Setting                       | Effect |
|-------------------------------|--------|
| `large-v3` model              | The most accurate of the Whisper family. |
| Forced language `fr`          | Avoids language-detection errors. |
| `beam_size = 8`               | Wide beam search → safer decoding. |
| Temperature fallback          | Retries on repetitive/incoherent output. |
| **VAD** filter (Silero)       | Strips silences → fewer hallucinations. |
| `condition_on_previous_text`  | Keeps context between segments. |

By default, inference runs on **CPU** in `int8` (the sweet spot between accuracy
and memory). This is the case for every installed copy of the app: the bundled
CTranslate2 engine is the CPU-only build, so no GPU is used even if one is
present.

### ⚡ Optional GPU acceleration

The engine behind the app (CTranslate2) can run on a GPU — **NVIDIA (CUDA)** or
**AMD (ROCm/HIP)**. It is *opt-in* and requires installing a different engine
build yourself; the installer stays CPU-only so it works on any machine.

Once the GPU build is installed, enable it with an environment variable:

```powershell
$env:TVFR_DEVICE = "cuda"     # "auto" (default) | "cpu" | "cuda"
$env:TVFR_COMPUTE = "float16" # optional; float16 is chosen automatically on GPU
```

`cuda` covers **both** vendors — CTranslate2 uses that single device name for
NVIDIA and AMD alike. On GPU the app switches from `int8` to `float16`, which is
both faster *and* more precise; `large-v3` needs roughly 4 GB of VRAM.

If the GPU cannot be initialised for any reason, the app logs the cause and
falls back to CPU instead of failing.

The command-line tool exposes the same choice:

```powershell
python transcribe.py audio.mp3 --device cuda
```

<details>
<summary>AMD Radeon setup (RDNA2+, e.g. RX 7900 XT) on Windows</summary>

Requires a recent AMD Adrenalin driver and Python 3.12.

```powershell
# 1. ROCm 7.2.1 runtime
pip install --no-cache-dir --no-deps `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm-7.2.1.tar.gz

# 2. ROCm build of CTranslate2, over the CPU/CUDA one
#    from https://github.com/OpenNMT/CTranslate2/releases/tag/v4.7.1
#    (asset: rocm-python-wheels-Windows.zip)
pip install ctranslate2-4.7.1-cp312-cp312-win_amd64.whl --force-reinstall --no-deps

# 3. Check the GPU is visible
python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Known limitation: on RDNA3 (gfx1100) the CTranslate2 model destructor can
deadlock ([CTranslate2#2038](https://github.com/OpenNMT/CTranslate2/issues/2038)).
The app works around it by keeping a retired model alive, so changing model or
compute type mid-session leaves the previous one in VRAM until restart.

</details>

---

## 🛠 Development (from source)

```powershell
# 1. Clone
git clone https://github.com/Adrien10200/transcription-vocale-fr.git
cd transcription-vocale-fr

# 2. Virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Dependencies (PyAV bundles FFmpeg — no external ffmpeg needed)
pip install -r requirements.txt

# 4. Run
python app.py
```

### Command line (no GUI)

```powershell
python transcribe.py "C:\path\to\audio.mp3"      # one file
python transcribe.py "C:\audio_folder" --srt      # whole folder + subtitles
```

Options: `--model`, `--language`, `--beam-size`, `--compute-type`, `--prompt`,
`--output`. See `python transcribe.py --help`.

---

## 📦 Build the executable

```powershell
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean app.spec
# Output: dist/Transcription Vocale FR/Transcription Vocale FR.exe
```

The [GitHub Actions CI](.github/workflows/build-release.yml) does the same and
publishes a **release** on every `v*` tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

---

## 🗂 Project structure

```
├── app.py                 # GUI application (PySide6) + themes + i18n + icon
├── transcriber_core.py    # Transcription core (faster-whisper)
├── transcribe.py          # Command-line interface
├── app.spec               # PyInstaller build recipe
├── assets/                # icon.svg / icon.ico / icon.png
├── requirements.txt       # Runtime dependencies
├── requirements-build.txt # Build dependencies
├── tools/                 # Optional local tooling (not versioned)
├── models/                # Model cache (~3 GB, not versioned)
└── .github/workflows/     # CI: Windows build + release
```

---

## ❓ FAQ

<details>
<summary><b>Why is the first launch slow?</b></summary>
<br/>
The <code>large-v3</code> model (~3 GB) downloads once. After that, only the
transcription time matters.
</details>

<details>
<summary><b>Does it work without an Internet connection?</b></summary>
<br/>
Yes, once the model is downloaded. No audio data is ever sent online.
</details>

<details>
<summary><b>Which formats are supported?</b></summary>
<br/>
Anything ffmpeg can decode: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, WMA, MP4, MKV,
MOV, AVI, WEBM…
</details>

---

## 📄 License

Released under the [MIT](LICENSE) license.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) ·
[OpenAI Whisper](https://github.com/openai/whisper) ·
[PySide6](https://www.qt.io/qt-for-python) ·
[ffmpeg](https://ffmpeg.org/).

<br/>

---

<a name="-français"></a>

<div align="center">

# 🇫🇷 Français

**🌍 Langue :** [English](#french-voice-transcription) · **Français**

</div>

Transcrivez votre voix française en texte — haute précision, 100 % en local.
Application de bureau simple et moderne, propulsée par
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) et le modèle
`large-v3` d'OpenAI Whisper. Vos fichiers audio ne quittent jamais votre ordinateur.

### ✨ Fonctionnalités

- 🎯 **Haute précision en français** — modèle `large-v3`, recherche par faisceau, repli sur la température, détection d'activité vocale (VAD).
- 🖱 **Glisser-déposer** un fichier audio/vidéo, ou cliquer pour parcourir.
- 🎙 **Enregistrement micro ou son du bureau** — *Enregistrer* (puis transcrire) ou *Direct* (le texte apparaît en parlant) ; capturez votre micro **ou l'audio système** (loopback WASAPI) via le sélecteur.
- 🔒 **100 % hors ligne** — aucune donnée ne quitte votre machine.
- ⚡ **Interface fluide** — transcription en arrière-plan, texte affiché en direct, **annulable** à tout moment.
- 📋 **Copier / Enregistrer** le résultat en un clic (`.txt` ou sous-titres `.srt`).
- 📝 **Corrections personnalisées** — apprenez votre vocabulaire à l'app (ex. `Volio` → `Voelio`) ; les remplacements sont appliqués automatiquement et **conservés après une mise à jour**.
- 🗣 **Identification des interlocuteurs** — diarisation légère optionnelle qui marque les tours de parole (`Interlocuteur 1 / 2…`), 100 % hors-ligne.
- 📦 **Installeur** — installation en un clic ; le cache du modèle est stocké **hors** du dossier de l'app, donc les mises à jour ne re-téléchargent jamais les ~3 Go.
- 🎨 **3 thèmes** — 🌙 Sombre · ☀️ Clair · 🎃 Halloween.
- 🌍 **Interface bilingue** — basculez entre anglais et français en un clic.
- 🎬 **Multi-formats** — MP3, WAV, M4A, FLAC, OGG, MP4, MKV, MOV… (décodage intégré via PyAV, sans ffmpeg externe).
- 🪶 **Léger** — application ~270 Mo (au lieu de 750 Mo), plus le cache du modèle.

### 🚀 Installation (utilisateur final)

1. Ouvrez l'onglet [**Releases**](https://github.com/Adrien10200/transcription-vocale-fr/releases/latest).
2. Téléchargez `Transcription-Vocale-FR-…-win64.zip`.
3. Décompressez-le où vous voulez.
4. Double-cliquez sur **`Transcription Vocale FR.exe`**.

> 💡 **Premier lancement :** le modèle `large-v3` (~3 Go) est téléchargé
> automatiquement puis mis en cache dans `%LOCALAPPDATA%\TranscriptionVocaleFR\models`.
> Les fois suivantes sont immédiates, et **mettre à jour l'application ne
> re-télécharge jamais le modèle** — le cache est stocké hors du dossier de l'app.

#### ⚠️ Avertissement Windows SmartScreen

L'app est signée avec un **certificat auto-signé** : Windows peut afficher un
écran bleu **« Windows a protégé votre ordinateur »** au premier lancement.
C'est normal pour une application non signée par une autorité commerciale.
Pour l'exécuter : cliquez sur **Informations complémentaires** puis
**Exécuter quand même**. Utilisez le bouton **Vérifier les mises à jour** dans
l'app pour obtenir les nouvelles versions.

### 🖥 Utilisation

| Étape | Action |
|:-----:|--------|
| **1** | **Glissez** votre fichier audio sur la zone (ou cliquez pour parcourir). |
| **2** | Choisissez la qualité — par défaut **Qualité max (large-v3)**. |
| **3** | Cliquez sur **Transcrire**. Le texte apparaît en direct. |
| **4** | **Copiez** ou **Enregistrez** le résultat une fois terminé. |

Le thème et la langue se changent à tout moment en haut à droite.

### 🛠 Développement

```powershell
git clone https://github.com/Adrien10200/transcription-vocale-fr.git
cd transcription-vocale-fr
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Aucun ffmpeg externe requis : PyAV embarque les bibliothèques FFmpeg.
python app.py
```

### 📦 Compiler l'exécutable

```powershell
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean app.spec
```

La CI publie une release à chaque tag `v*` : `git tag v1.0.0 && git push origin v1.0.0`.

### 📄 Licence

Distribué sous licence [MIT](LICENSE).
