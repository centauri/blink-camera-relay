# v0.1.2

Enable mapped Outdoor 4 settings that were previously read-only:

- Motion sensitivity (1-9), retrigger delay (10-60 seconds), speaker volume (1-8).
- Motion clip length from 5 seconds to the camera-reported maximum, using a slider.
- Status LED, infrared intensity and source video quality.
- Photo Capture interval from camera-reported options and automatic thumbnail updates.

Uses the Blink app's shared-camera wire fields and encodings, preserves model
capability checks, and verifies requested values by reading configuration back.
Unsupported spotlight/image-flip controls and diagnostic fields remain read-only.
Photo features can still require a Blink subscription or trial.

Mappings were checked against the signed Android app and a live Outdoor 4
configuration read. Automated tests cover outgoing requests and read-back;
physical settings were not changed during development. Mini behavior is retained.
See docs/outdoor4-settings.txt for mapping evidence and scope.

Update ghcr.io/centauri/blink-camera-relay:latest (or pin :v0.1.2), keep appdata,
and reload camera settings in the dashboard.
