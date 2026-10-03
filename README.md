# Blink Camera Relay

Unofficial Blink live view to RTSP and ONVIF, with web onboarding and camera
settings. **One container** includes the dashboard, BlinkPy/IMMIS worker, FFmpeg,
MediaMTX and ONVIF adapter. Blink cloud pairing/login is still required.

## Unraid

Use [the Unraid template](unraid/blink-camera-relay.xml) with image
`ghcr.io/centauri/blink-camera-relay:edge`. The container targets linux/amd64.
The template is provided here; it has not been submitted to Community Apps.

- Network: host, for ONVIF multicast discovery.
- Appdata: `/mnt/user/appdata/blink-camera-relay` mounted at `/data`.
- `BRIDGE_HOST`: your Unraid server's LAN IPv4 address.
- `BRIDGE_ADMIN_PASSWORD`: choose at least 12 characters.
- Web UI: `http://YOUR_SERVER_IP:8787`, username `admin` and that password.

Pair the camera in Blink's app first. Open the bridge UI, complete Blink login
and 2FA, choose a camera and RTSP path, then start its stream and ONVIF service.
The UI generates each camera's unique ONVIF identity. Enabled services resume
on container restart. Tokens/settings persist in appdata; process IDs and logs
are ephemeral. Stop the old Windows bridge before adopting the same camera
through the new installation. Do not copy its saved process/runtime files.

Use a trusted LAN: dashboard HTTP Basic authentication does not encrypt network
traffic. RTSP/ONVIF have no enforced client authentication. Do not forward these
ports to the Internet. For remote administration use a trusted VPN or TLS proxy.

Host ports must be free: TCP 8787 (UI), 8554 (internal source), 8555 (LAN RTSP),
8080 (default ONVIF, adjustable per camera), and UDP 3702 (discovery).
VLC can use `rtsp://YOUR_SERVER_IP:8555/CAMERA_ID`; the UI shows the exact URL.

## Compose alternative

Copy `.env.example` to `.env`, fill the LAN IP/password, and run:

```sh
mkdir -p data
chmod 700 data
docker compose up -d
```

No separate MediaMTX or ONVIF containers are needed. For a local build use
`docker compose up -d --build`. Shutdown allows up to 90 seconds for cleanup.
An optional independently verified IMMIS certificate pin can be passed using
`BLINK_IMMIS_CERT_SHA256`; normal TLS verification remains enabled.

## Windows

The native Windows dashboard still works: install Python 3.12+, Node 22+,
FFmpeg and MediaMTX, create `.venv`, install `requirements.lock` and
`./vendor/blinkpy`, run `npm ci --prefix vendor/onvif` and compile TypeScript,
then run `Start-Dashboard.ps1`. Native mode stays loopback-only.

## Builds and dependency sources

GitHub Actions publishes just `ghcr.io/centauri/blink-camera-relay`.
Main builds use `edge`; version tags publish `latest` and their version. Every
build also has a `sha-COMMIT` tag. Inline attestations are disabled to avoid
GHCR's non-runnable `unknown/unknown` platform entries. ARM is not yet built.

Matching Debian dependency sources, patches/build rules, notices and checksums
are downloadable under Releases, in `sources-COMMIT`. These are archives, not
container images or services. The image label `io.blink-camera-relay.sources`
links to its exact archive. Sources publish before the runtime image; keep them
available for as long as the matching binaries are distributed. Previously
published standalone/source-image packages are legacy and are no longer built.

## Limits and validation

Mini 2K+ live streaming and Protect adoption have been exercised on Windows.
Cloud session renewals can cause gaps; other camera models and uninterrupted
recording are not guaranteed. No firmware modifications or entitlement bypass
are included. Settings are capability-gated and read back; not every physical
setting effect is verified.

The regression suite has 64 tests. CI also compiles ONVIF, audits npm dependencies,
checks the release files, tests H.264 encoding and boots the integrated dashboard
with authentication checks. Hardware and Unraid deployment are separate checks.
See LICENSE, NOTICE, THIRD-PARTY.md and SECURITY.md for scope and attribution.
