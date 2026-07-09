"""Version unique de l'application (source de vérité).

Utilisée par :
  • l'interface (affichage + bouton « Vérifier les mises à jour »),
  • les métadonnées de l'exécutable Windows,
  • l'installeur Inno Setup (via --DMyAppVersion en CI).
"""

__version__ = "1.6.0"

# Dépôt GitHub utilisé pour vérifier les nouvelles versions.
GITHUB_OWNER = "Adrien10200"
GITHUB_REPO = "transcription-vocale-fr"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
