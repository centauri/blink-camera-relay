# Blink Camera Relay

Unofficial Blink live-view Ã¢â€ â€™ RTSP Ã¢â€ â€™ ONVIF bridge for UniFi Protect.
Uses BlinkPy's authenticated IMMIS livestream; it does not replay motion clips,
flash firmware, remove cloud dependence, or bypass subscription entitlement.

## Status

Mini 2K+ live video and Protect adoption have been exercised on Windows.
Normal sessions still end and require renewal, producing gaps. Other camera
models are not guaranteed. The Windows dashboard supports onboarding, settings,
and telemetry. Containers currently provide the command-line streaming worker
and ONVIF adapter, **not the dashboard**. No unattended CCTV guarantee is made.

## Docker / Unraid

Requires Docker Compose v2 and an x86-64 host. Copy `.env.example` to `.env`,
replace the documentation-only server IP with your actual LAN address, and
create a private `data` directory. Pair the camera using Blink's app first.

```sh
mkdir -p data
chmod 700 data
cp .env.example .env
# Edit .env before starting services.
docker compose --profile tools build auth
docker compose run --rm auth
docker compose run --rm auth list
```

Set BLINK_CAMERA_NAME or BLINK_CAMERA_SERIAL, and RTSP_PATH in `.env`.
The auth command prompts for credentials and 2FA; account state stays in data/.

```sh
docker compose --profile live up -d mediamtx bridge
```

Open `rtsp://YOUR_SERVER_IP:8554/blink-mini` in VLC using RTSP over TCP.
For a camera-free test, stop bridge and use the `test` profile's test-source.

After the first successful Actions build, set BRIDGE_IMAGE to
`ghcr.io/centauri/blink-camera-relay:edge` and ONVIF_IMAGE to
`ghcr.io/centauri/blink-camera-relay-onvif:edge`, then use `docker compose pull`.
Private GHCR images require a GitHub login with package-read permission.

For ONVIF, reserve a separate unused LAN IP, generate a unique ONVIF_UUID and
locally administered ONVIF_MAC, and set the existing Unraid LAN network name.
Then add `-f compose.yaml -f compose.onvif.yaml` to Compose commands. macvlan/LAN
multicast requires host-specific setup; Docker Desktop networking is not an
Unraid substitute. Do not expose these unauthenticated camera ports publicly.

## Windows dashboard

Install Python 3.12+, Node.js 22+, FFmpeg and MediaMTX from their official sources.
Make ffmpeg, mediamtx and node available on PATH. Then:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock ./vendor/blinkpy
npm ci --prefix vendor/onvif
npx --prefix vendor/onvif tsc --project vendor/onvif/tsconfig.json
.\Start-Dashboard.ps1
```

The dashboard is at http://127.0.0.1:8787. It guides sign-in, 2FA, camera selection
and local stream setup. Secrets remain on this computer. Worker processes outlive
the browser/dashboard; stop streams using the UI before shutting down services.
Camera settings use strict types, mapped ranges and read-back checks. Untested
models/encodings remain read-only. Physical effects are not all verified.

## Builds and source availability

Actions tests Python code and compiles TypeScript, then builds amd64 images.
Pull requests build without publishing; main pushes publish GHCR images with
`edge` and immutable `sha-COMMIT` tags; version tags publish `latest` plus the version. SBOM and provenance are generated.
The sources images are published before their corresponding runtime images.
They contain exact Debian source archives, Debian patches/build rules, package
versions, checksums and notices, including FFmpeg and its Debian dependencies.

To extract corresponding sources (use the exact runtime commit tag):

```sh
docker pull ghcr.io/centauri/blink-camera-relay-sources:sha-COMMIT
id=$(docker create ghcr.io/centauri/blink-camera-relay-sources:sha-COMMIT /unused)
docker cp "$id:/sources" ./corresponding-sources
docker rm "$id"
```

The ONVIF companion is `blink-camera-relay-onvif-sources:sha-COMMIT`.
Retain source images for as long as their binary tags are distributed. A rebuild
must publish matching source images too. See THIRD-PARTY.md and NOTICE for the
scope of the root license and third-party terms.

## Validation

62 Python regression tests passed before release preparation. Release validation
also scans tracked files for prohibited private artifacts. Docker/Actions build
results must be checked before treating an image as tested. See SECURITY.md for
network and credential limitations, and CONTRIBUTING.md for development checks.

Release-channel separation and nested build-context regression checks were inspired by the maintainer’s WeatherNode deployment practices; no WeatherNode application code is included. Old source images are intentionally not automatically deleted.
