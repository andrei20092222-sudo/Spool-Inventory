"""Constants for the Spool Inventory integration."""

from __future__ import annotations

DOMAIN = "spool_inventory"

STORAGE_KEY = f"{DOMAIN}.spools"
STORAGE_VERSION = 2  # 2: settings, own catalog, trash, archive and weigh dates were added
STORAGE_MINOR_VERSION = 1
# Safety copies kept in .storage next to the main file.
BACKUP_KEY = f"{DOMAIN}.backup_daily"  # refreshed at most once a day
PRE_MIGRATION_KEY = f"{DOMAIN}.backup_before_upgrade"  # the file as it was before a format upgrade
PRE_IMPORT_KEY = f"{DOMAIN}.backup_before_restore"  # everything as it was before "Replace everything"
EXPORT_FORMAT = "spool_inventory_backup"
TRASH_MAX = 25  # deleted spools that can still be restored
MAX_PRINTERS = 5
MAX_TASKS = 200
MAX_ITEMS = 300
EVENT_TASK_DUE = f"{DOMAIN}_task_due"
EVENT_ITEM_LOW = f"{DOMAIN}_item_low"
HISTORY_MAX = 2000  # log entries kept (oldest are dropped)
SAVE_DELAY = 2  # seconds; writes are debounced

DEFAULT_COLOR_HEX = "#808080"
DEFAULT_DIAMETER = 1.75
DEFAULT_INITIAL_WEIGHT = 1000.0

SIGNAL_SPOOL_ADDED = f"{DOMAIN}_spool_added"
SIGNAL_SPOOL_REMOVED = f"{DOMAIN}_spool_removed"

PANEL_URL_PATH = "spool-inventory"
PANEL_WEBCOMPONENT = "spool-inventory-panel"
STATIC_URL = "/spool_inventory_static"
SIGNAL_INVENTORY_CHANGED = f"{DOMAIN}_inventory_changed"

# Events fired on the Home Assistant bus when a spool gets low / runs out.
EVENT_LOW = f"{DOMAIN}_low"
EVENT_EMPTY = f"{DOMAIN}_empty"

DEFAULT_SETTINGS = {
    "low_threshold": 150.0,  # g; a spool below this (and above 0) is "low"
    "currency": "RON",  # shown next to prices and the stock value
    "notify": True,  # create a persistent notification when a spool gets low / empty
    "locations": ["Bedroom storage", "Drier", "Small bedroom storage"],
}
MAX_USER_CATALOG = 500


def signal_spool_updated(spool_id: str) -> str:
    """Return the dispatcher signal for changes to one spool."""
    return f"{DOMAIN}_spool_updated_{spool_id}"
