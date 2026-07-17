# nano-trader-ai

Micro-bot di investimento algoritmico autonomo assistito da IA per piccoli importi.

## Obiettivo del Progetto
Sviluppare un sistema leggero e modulare in Python che si interfacci tramite API con Alpaca Markets per eseguire operazioni automatizzate in modalità Paper Trading (frazioni di azioni ed ETF).

## Requisiti di Sviluppo (per l'Agente AI)
- **Linguaggio:** Python 3.11+
- **Librerie Core:** `alpaca-py`, `python-dotenv`, `pandas`
- **Architettura:** Struttura modulare con netta separazione tra:
  - `config/`: Gestione variabili d'ambiente.
  - `client/`: Connessione alle API Alpaca.
  - `strategy/`: Logica algoritmica di analisi e decisionale.
  - `execution/`: Invio e monitoraggio degli ordini di acquisto/vendita.
- **Sicurezza:** Le chiavi API (`APCA-API-KEY-ID` e `APCA-API-SECRET-KEY`) devono essere lette esclusivamente dal file `.env` (escluso dal tracking).
- **Infrastruttura:** Ottimizzato per l'esecuzione serverless (es. PythonAnywhere Free o script pianificato localmente).
- **Testing:** Includere test unitari e di integrazione usando `pytest` per validare il parsing dei dati di mercato e la connettività.