"""Constants for the Rusclimate integration."""

from __future__ import annotations

from dataclasses import dataclass

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
DEVICE_TYPE_BREEZER_ASP200 = 59


@dataclass(frozen=True, kw_only=True)
class Profile:
    """What differs between device types."""

    model: str
    speed_max: int
    # The local UDP codec was verified on type 69 only; other types stay on the cloud channel.
    local: bool
    melody: bool
    # PM2.5 sensor, pre-filter, ionizer, UV lamp and damper.
    purifier: bool


PROFILES: dict[int, Profile] = {
    DEVICE_TYPE_BREEZER_ASP100: Profile(
        model="Ballu ONEAIR ASP-100 / Electrolux EASP-100",
        speed_max=7,
        local=True,
        melody=True,
        purifier=False,
    ),
    # Verified live on an ASP-200S, module firmware 1.21, over the cloud channel only.
    DEVICE_TYPE_BREEZER_ASP200: Profile(
        model="Ballu ONEAIR ASP-200S", speed_max=8, local=False, melody=False, purifier=True
    ),
}
SUPPORTED_DEVICE_TYPES = set(PROFILES)

MANUFACTURER = "Rusclimate"
MODELS = {device_type: profile.model for device_type, profile in PROFILES.items()}
