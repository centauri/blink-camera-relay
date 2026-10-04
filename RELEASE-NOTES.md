# v0.1.0

First versioned public release of Blink Camera Relay for Unraid.

- One container with web onboarding, camera controls, live preview, RTSP and ONVIF.
- Automatic verification for supported Blink IMMIS servers using the public
  certificate authenticated against Blink's signed Android app.
- Persistent configuration and optional certificate fingerprint overrides.
- Docker smoke tests cover packaged certificate trust and rejection of unrelated certificates.

Image: `ghcr.io/centauri/blink-camera-relay:v0.1.0`.
The `latest` tag follows versioned releases; `edge` follows development builds.

Existing Unraid installations using `edge` can change Repository to
`ghcr.io/centauri/blink-camera-relay:latest` and apply the update. Keep the existing
appdata mapping. A manual `BLINK_IMMIS_CERT_SHA256` override is no longer needed
for the supported certificate, but remains compatible.

Blink cloud pairing and authentication remain required. Session renewal can cause
video gaps. The published image supports linux/amd64; other regions' certificates
and all camera models have not been independently tested.
