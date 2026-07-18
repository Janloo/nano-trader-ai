@echo off
echo ===================================================
echo   NANO-TRADER-AI : WEEKEND AUTOPILOT
echo ===================================================
echo.
echo Avvio in corso... Assicurati di avere Internet attivo.
echo Il bot rimarra' acceso. Premi CTRL+C per fermarlo.
echo.

:: Attiva l'ambiente virtuale
call .venv\Scripts\activate.bat

:: Esegue la prima analisi macro per avere un Bias fresco
echo [1/2] Sto svegliando l'Intelligenza Artificiale (Macro Analysis)...
python main_macro.py

echo.
echo [2/2] Avvio del Motore di Trading in Tempo Reale (Crypto)...
:: Questo comando resta in ascolto all'infinito
python realtime_executor.py

pause
