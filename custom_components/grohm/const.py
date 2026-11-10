"""Costanti dell'integrazione Grohm."""

from datetime import timedelta

DOMAIN = "grohm"
MANUFACTURER = "Grohm"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30  # secondi
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# Ogni quanto ricontrollare l'elenco delle wallbox (nuove/rimosse).
DISCOVERY_INTERVAL = timedelta(minutes=10)

# Dopo un comando la wallbox impiega qualche secondo a riportare lo stato.
COMMAND_REFRESH_DELAY = 3
