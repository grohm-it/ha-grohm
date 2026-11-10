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
# Chargers take a few seconds to report the result of a command.
COMMAND_REFRESH_DELAY = 3

# Installers only have read-only access to the chargers of their customers,
# so they are not supported.
SUPPORTED_ACCOUNT_TYPES = (AccountType.PRIVATE, AccountType.MANAGER)
