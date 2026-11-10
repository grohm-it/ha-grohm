# Grohm Wallbox per Home Assistant

Integrazione personalizzata (custom component) che porta in Home Assistant le
wallbox Grohm associate a un account **my-Grohm**, usando lo stesso backend
GraphQL dell'app (`https://api.grohm.it/graphql`).

> Nota: in Home Assistant gli "add-on" sono container del Supervisor; per
> creare dispositivi ed entità serve invece un'**integrazione**, che è ciò che
> trovi qui. Funziona su qualunque installazione (OS, Container, Core).

## Cosa espone

Solo le **wallbox fisiche**: ogni wallbox è un dispositivo in HA. Le **reti**
del gestore non vengono create: servono solo a scoprire le wallbox (quelle di
tutte le reti più quelle non assegnate a nessuna rete).

| Entità | Tipo | Note |
|---|---|---|
| Stato | sensore (enum) | Pronta / In carica / In pausa / In attesa / Finita |
| Potenza | sensore W→kW | campo `energyCar`; 0 se non in carica (come l'app) |
| Energia sessione | sensore kWh | `wattHoursCharged` della sessione corrente |
| Energia totale | sensore kWh | `totalKwhCharged`, adatto alla dashboard Energia |
| Corrente auto / Corrente massima | sensore A | |
| Tensione | sensore V | il backend la dà in millivolt (stringa) |
| Durata ricarica, Inizio sessione | sensori | inizio sessione disattivato di default |
| Fasi in uso | sensore | solo wallbox trifase, durante la ricarica |
| Segnale Wi-Fi, Potenza nominale, Tariffa energia | diagnostica | |
| Connettività, In carica | sensori binari | |
| Blocco | lock | blocca/sblocca la wallbox (`editDevice.locked`) |
| Ricarica | switch | spento = pausa, acceso = riprendi; disponibile solo con auto collegata (In carica / In pausa / In attesa) |
| Forza ricarica + Ricarica forzata attiva | pulsante + binario | **solo account gestore**, solo a wallbox Pronta; la wallbox la mantiene per 300 s |

Le entità di una wallbox offline diventano *non disponibili*, tranne
connettività, energia totale e dati di configurazione.

## Account supportati

- **Privato** e **gestore**: sì.
- **Installatore**: **no**. Il login viene rifiutato nella configurazione
  (e la sessione appena aperta viene chiusa subito). Se un account già
  configurato diventa installatore, l'integrazione smette di caricarsi.
- Account senza tipo (creati dalla webapp e mai completati): rifiutati, finché
  non si sceglie il tipo dall'app my-Grohm.

## Installazione

**HACS** (repository personalizzato): aggiungi l'URL del repository come
*Integration*, installa "Grohm Wallbox" e riavvia Home Assistant.

**Manuale**: copia `custom_components/grohm` nella cartella
`config/custom_components/` di Home Assistant e riavvia.

Poi: *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Grohm
Wallbox* e inserisci email e password dell'app my-Grohm.

Opzioni: intervallo di aggiornamento (default 30 s, min 10 s). L'elenco delle
wallbox viene ricontrollato ogni 10 minuti: le nuove compaiono da sole.

## Come funziona

- Autenticazione a **cookie di sessione** (come l'app): email e password sono
  salvate nella config entry di HA e usate per rifare il login quando la
  sessione scade (`me` torna `null` o il server risponde 401/403). Se la
  password cambia, HA chiede di riautenticarsi.
- Ogni integrazione usa una propria sessione HTTP con cookie jar separato.
- Nessuna subscription nel backend: lo stato è letto in **polling**, con una
  sola query GraphQL per tutte le wallbox (alias `d0`, `d1`, …).
- Comandi: `changeDeviceStatus` con la stessa mappatura della webapp
  (`CHARGING→PAUSED`, `PAUSED→RUNNING`, `WAITING→RESUMED`), `editDevice` per
  blocco e ricarica forzata. Dopo ogni comando lo stato viene riletto dopo 3 s.

## Sviluppo e test

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

I test usano un backend GraphQL finto (`tests/conftest.py`): coprono login e
rifiuto degli installatori, scoperta delle wallbox (privato e gestore),
nuovo login a sessione scaduta, entità, comandi e riautenticazione.

## Verifiche sul backend reale

Confrontato con lo schema di `api.grohm.it` (introspection) e con risposte vere:
tutti i campi e le mutation usati esistono con i tipi attesi; senza sessione il
server risponde HTTP 200 con `"User is not authenticated"` (o `me: null`),
credenziali errate → `LoginError "Invalid email or password"`. Il flusso con
un account reale (privato e gestore) resta da provare.

## Percorso di pubblicazione

**1. HACS (repository personalizzato)** — già possibile appena il repo è
pubblico su GitHub: basta aggiungerne l'URL in HACS.

**2. Lista predefinita HACS** — servono: repo pubblico con descrizione e
topic, almeno una GitHub Release, workflow `hassfest` e `hacs/action` verdi
(già in `.github/workflows/`), logo e icona nel repo
[home-assistant/brands](https://github.com/home-assistant/brands), poi una PR
a [hacs/default](https://github.com/hacs/default).

**3. Integrazione ufficiale (core)** — requisiti aggiuntivi:
- spostare `api.py` in una **libreria Python pubblicata su PyPI** (licenza
  OSI, rilasci automatici da CI) e dichiararla in `requirements` del manifest;
- codice, commenti e `strings.json` in inglese (le altre lingue arrivano da
  Lokalise, non dal repo);
- prima PR con **una sola piattaforma** (es. `sensor`), le altre in PR
  successive; requisiti del livello *Bronze* della Integration Quality Scale
  (config flow testato al 100%, unique id, `runtime_data`, ecc.);
- PR della documentazione su `home-assistant.io` e brand come al punto 2.
