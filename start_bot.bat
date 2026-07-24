@echo off
echo ===================================================
echo   NANO-TRADER-AI : FULL SYSTEM STARTUP
echo ===================================================
echo.

:: Controllo di sicurezza: verifica se il bot è già in esecuzione
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter 'Name = ''python.exe''' | Where-Object { $_.CommandLine -match 'realtime_executor\.py' }) { exit 1 } else { exit 0 }"
if %errorlevel% equ 1 (
    echo [ERRORE di SICUREZZA]
    echo Un'istanza del bot e' gia' in esecuzione! 
    echo Avviare istanze multiple puo' causare problemi con Alpaca ^(connection limit exceeded^).
    echo.
    echo Per favore, chiudi il bot attualmente in esecuzione prima di avviarne uno nuovo.
    pause
    exit /b
)

echo Avvio in corso...
echo.
:: Avvia il server della Dashboard in una nuova finestra in background
echo [1/3] Avvio del Server della Dashboard (su porta 8080)...
start "Nano-Trader Dashboard Server" cmd /c ".\.venv\Scripts\activate.bat & python server.py"

:: Attiva l'ambiente virtuale nella finestra corrente
call .venv\Scripts\activate.bat

:: Esegue l'analisi macro iniziale
echo [2/3] Sveglio l'Intelligenza Artificiale (Macro Analysis)...
python main_macro.py

echo.
echo [3/3] Avvio del Motore di Trading in Tempo Reale (Crypto)...
:: Questo comando resta in ascolto all'infinito
python realtime_executor.py

pause
