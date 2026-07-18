@echo off
echo ===================================================
echo   NANO-TRADER-AI : FULL SYSTEM STARTUP
echo ===================================================
echo.
echo Avvio in corso...
echo.

:: Avvia il server della Dashboard in una nuova finestra in background
echo [1/3] Avvio del Server della Dashboard (su porta 8000)...
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
