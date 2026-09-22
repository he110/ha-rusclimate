"""Parse the "Share" link from the Hommyn app. No Home Assistant imports.

The link is the only secret we need: its token authorises both the cloud MQTT topics and the
local UDP handshake. Format:
rusklimat://device-share/rusclimate/<DEVTYPE>/<MAC12>?token=<32hex>&name=...&deviceRoom=...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_MAC12 = re.compile(r"^[0-9a-f]{12}$")


class InvalidShareLink(ValueError):
    """The text is not a Hommyn device share link."""


@dataclass(frozen=True, slots=True)
class ShareLink:
    vendor: str
    device_type: int
    mac: str  # 12 lowercase hex chars, no separators
    token: str  # 32 lowercase hex chars
    name: str | None = None
    room: str | None = None
    location: str | None = None
    model: str | None = None


def parse_share_link(text: str) -> ShareLink:
    text = text.strip()
    # The app sometimes wraps the link into a sentence; take the first rusklimat:// token.
    if (start := text.find("rusklimat://")) > 0:
        text = text[start:].split()[0]
    parts = urlsplit(text)
    if parts.scheme != "rusklimat" or parts.netloc != "device-share":
        raise InvalidShareLink("not a rusklimat://device-share link")
    segments = [unquote(s) for s in parts.path.strip("/").split("/")]
    if len(segments) != 3:
        raise InvalidShareLink("expected /<vendor>/<devtype>/<mac>")
    vendor, devtype, mac = segments
    mac = mac.lower().replace(":", "").replace("-", "")
    if not devtype.isdigit() or not _MAC12.match(mac):
        raise InvalidShareLink("bad device type or MAC")
    query = parse_qs(parts.query)
    token = (query.get("token") or [""])[0].lower()
    if not _HEX32.match(token):
        raise InvalidShareLink("missing or malformed token")

    def opt(key: str) -> str | None:
        return (query.get(key) or [None])[0] or None

    return ShareLink(
        vendor=vendor,
        device_type=int(devtype),
        mac=mac,
        token=token,
        name=opt("name"),
        room=opt("deviceRoom"),
        location=opt("deviceLocation"),
        model=opt("attributes_model"),
    )


def format_mac(mac: str) -> str:
    """112233445566 -> 11:22:33:44:55:66"""
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))
