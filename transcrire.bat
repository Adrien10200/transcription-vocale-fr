@echo off
REM ===================================================================
REM  Lanceur de transcription francaise -> texte brut.
REM
REM  Utilisation :
REM    - Glisser-deposer un fichier audio/video sur ce .bat, OU
REM    - Double-cliquer puis saisir le chemin, OU
REM    - En ligne de commande :  transcrire.bat "audio.mp3"
REM ===================================================================
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%transcribe.py"

if not exist "%PY%" (
    echo [!] Environnement Python introuvable : %PY%
    echo     Relancez l'installation.
    pause
    exit /b 1
)

if "%~1"=="" (
    set /p "TARGET=Chemin du fichier audio/video a transcrire : "
) else (
    set "TARGET=%~1"
)

if "%TARGET%"=="" (
    echo [!] Aucun fichier fourni.
    pause
    exit /b 1
)

echo.
echo === Transcription en cours (large-v3, haute precision) ===
echo.
"%PY%" "%SCRIPT%" "%TARGET%" %2 %3 %4 %5 %6 %7 %8 %9

echo.
echo === Termine ===
pause
endlocal
