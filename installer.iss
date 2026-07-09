; ============================================================================
;  Installeur « Transcription Vocale FR » (Inno Setup)
;
;  - Installe l'application dans %LOCALAPPDATA%\Programs (aucun droit admin).
;  - Le cache du modèle (~3 Go) est stocké séparément dans
;    %LOCALAPPDATA%\TranscriptionVocaleFR\models : une MISE À JOUR de l'app
;    ne le supprime JAMAIS et ne le re-télécharge donc jamais.
;  - Crée les raccourcis Menu Démarrer + Bureau (optionnel).
; ============================================================================

#define MyAppName "Transcription Vocale FR"
#define MyAppExeName "Transcription Vocale FR.exe"
#ifndef MyAppVersion
  #define MyAppVersion "1.6.0"
#endif
#define MyAppPublisher "Adrien"
#define MyAppURL "https://github.com/Adrien10200/transcription-vocale-fr"

[Setup]
AppId={{B3F1C2A4-7E9D-4B2A-9C3E-TRANSCRIPTIONFR}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases

; Installation par utilisateur : pas de droits administrateur requis.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\TranscriptionVocaleFR
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}

; Le cache modèle est HORS du dossier d'installation : jamais touché aux MAJ.
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputBaseFilename=TranscriptionVocaleFR-Setup-{#MyAppVersion}
OutputDir=installer_output
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
SetupIconFile=assets\icon.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Tout le contenu du dossier PyInstaller onedir.
Source: "dist\Transcription Vocale FR\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Installation interactive : propose de lancer l'app à la fin.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Mise à jour silencieuse (auto-update) : relance l'app automatiquement.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallDelete]
; On NE supprime PAS le cache modèle : l'utilisateur peut réinstaller sans
; re-télécharger 3 Go. (Le dossier %localappdata%\TranscriptionVocaleFR reste.)
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
