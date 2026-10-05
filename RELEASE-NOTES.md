# v0.1.1

Fix missing configuration and capabilities for Outdoor 4 and other cameras
using Blink's shared camera API. Previously, settings discovery was restricted
to Mini-family devices and one older product identifier, even when video worked.

- Read shared camera configuration and zones by API family, without a product-name allowlist.
- Display additional signal, battery, temperature, network and capability information.
- Map shared motion-detection and infrared encodings separately from the Mini API.
- Enable mapped shared Boolean settings; preserve read-back verification and leave
  model-dependent ranges or unrecognized encodings read-only.
- Preserve existing Mini-family settings behavior.

Validated live configuration reads against Mini 2K+ (chickadee) and Outdoor 4
(sedona). Hardware settings were not modified during these checks. Automated
tests cover family routing, sanitization and write encoding; other hardware
models have not been independently tested. Doorbell configuration remains unmapped.

Update `ghcr.io/centauri/blink-camera-relay:latest`, or pin `:v0.1.1`.
Keep your existing appdata mapping and refresh camera settings in the dashboard.
