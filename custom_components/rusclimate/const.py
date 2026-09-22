"""Constants for the Rusclimate integration."""

from __future__ import annotations

DOMAIN = "rusclimate"

MDNS_TYPE = "_syncleo._udp.local."

CONF_SHARE_LINK = "share_link"
CONF_MAC = "mac"
CONF_DEVICE_TYPE = "device_type"
CONF_TOKEN = "token"  # noqa: S105 — config key name, not a secret
CONF_ROOM = "room"
CONF_CONN_MODE = "conn_mode"

# Device types this integration has an entity model for.
DEVICE_TYPE_BREEZER_ASP100 = 69
SUPPORTED_DEVICE_TYPES = {DEVICE_TYPE_BREEZER_ASP100}

MANUFACTURER = "Rusclimate"
MODELS = {DEVICE_TYPE_BREEZER_ASP100: "Ballu ONEAIR ASP-100 / Electrolux EASP-100"}
