# Changelog

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
