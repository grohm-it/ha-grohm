# Grohm for Home Assistant

The official Home Assistant integration for [Grohm](https://grohm.it) EV
chargers, made by Emme Esse S.p.A., the maker of Grohm. It connects to the
Grohm cloud with the account of the my-Grohm app.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=grohm&repository=ha-grohm&category=integration)

## Supported accounts

- **Private** accounts: all chargers of the account.
- **Fleet manager** accounts: the chargers of all networks, and the ones not
  in a network. Networks themselves are not added to Home Assistant.
- **Installer** accounts are not supported: they only have read-only access
  to the chargers of their customers. Sign in with the account of the owner.

## Installation

1. In Home Assistant, open **Settings > Marketplace**, search for **Grohm**
   and install it. Or use the button above.
2. Open **Settings > Devices & services > Add integration** and pick
   **Grohm**.
3. Enter the email address and password of your my-Grohm account.

To remove it, delete the entry in **Settings > Devices & services**, then
uninstall it from the Marketplace.

## Entities

Each charger is a device, with these entities:

| Entity | Notes |
|---|---|
| Status | Ready, charging, paused, waiting, finished |
| Power | 0 when not charging |
| Session energy, total energy | Total energy works in the Energy dashboard |
| Car current, maximum current, voltage | |
| Charging time, session start | Session start is disabled by default |
| Charging phases | Three phase chargers only, while charging |
| Rated power, energy price, Wi-Fi signal | Diagnostic; Wi-Fi signal disabled by default |
| Connectivity, charging, car | Binary sensors |
| Lock | A locked charger does not charge |
| Charging switch | Off pauses, on resumes. Available while a car is connected |
| Force charge button, forced charge sensor | Fleet manager accounts only, while the charger is ready. Lasts 300 seconds |

When a charger is offline, its entities become unavailable, except
connectivity, total energy and the configuration values.

## How it works

- The integration polls the Grohm cloud every 30 seconds, with one request
  for all chargers. It looks for new chargers every 10 minutes and adds them
  without a restart.
- When the password changes, Home Assistant asks you to sign in again.
- All communication goes through the [python-grohm](https://github.com/grohm/python-grohm)
  library.

## Known limitations

- Cloud only: without internet, or when the Grohm cloud is down, the
  entities are unavailable.
- Schedules, RFID cards and networks are managed in the my-Grohm app.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff
.venv/bin/pytest --cov=custom_components.grohm
.venv/bin/ruff check custom_components tests
```

The goal is to contribute the integration to Home Assistant Core. It already
follows the rules of the integration quality scale.

## License

Apache License 2.0, see [LICENSE](LICENSE). Grohm is a registered trademark
of Emme Esse S.p.A. This project is not affiliated with Home Assistant or the
Open Home Foundation.
