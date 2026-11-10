"""Constants for the Grohm integration."""

from datetime import timedelta
import logging

from grohm import AccountType

DOMAIN = "grohm"
LOGGER = logging.getLogger(__package__)

# The cloud gets fresh data from the chargers every few seconds while charging.
SCAN_INTERVAL = timedelta(seconds=30)
# How often to look for chargers that were added to or removed from the account.
DISCOVERY_INTERVAL = timedelta(minutes=10)
# After a command, the state is read again at this interval until the charger
# reports the change, for at most COMMAND_TIMEOUT seconds. Until then the
# entity shows the requested state. Chargers can take a while, a pause in
# particular.
COMMAND_POLL_INTERVAL = 4
COMMAND_TIMEOUT = 90

# Installers only have read-only access to the chargers of their customers,
# so they are not supported.
SUPPORTED_ACCOUNT_TYPES = (AccountType.PRIVATE, AccountType.MANAGER)
