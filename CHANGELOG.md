# Changelog

## 0.2.0

- New: a Repairs warning when a device has not been reachable over the local network for more than
  30 minutes (in Auto it keeps working through the cloud, so a broken local path would otherwise go
  unnoticed). It clears itself once the local connection is back.
- A second local session (for example this integration and a script on another machine) works in
  parallel; verified live.
- CO₂ sensor uses `UnitOfRatio.PARTS_PER_MILLION` (the old constant is deprecated in HA 2026.9).

## 0.1.1

- Adding a device manually no longer fails with "already in progress" while the same device waits
  in Discovered; the discovery is closed when the entry is created.

## 0.1.0

First release.

- Ballu ONEAIR ASP-100 / Electrolux EASP-100 breezers (Hommyn device type 69).
- Two channels: local network (Syncleo UDP, via `pysyncleo`) and the vendor cloud (MQTT).
- Connection mode per device: Auto (local first, cloud as fallback), Local only, Cloud only.
- Added by the Hommyn "Share" link; devices on the network are discovered automatically.
- Climate entity with presets, fan speed 1–7 and heater set point; supply air temperature, CO₂
  (when the sensor is fitted), filter resource, turbo end time, Wi-Fi signal and connection sensors;
  sound select; button sound and backlight auto-off switches; problem sensor.
- Sends the Home Assistant time zone when syncing the device clock (pysyncleo sends UTC).
