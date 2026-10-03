# onvif-protect-bridge

An ONVIF bridge that makes RTSP camera streams appear as genuine IP cameras in UniFi Protect.

[Docker Image](https://hub.docker.com/repository/docker/eddwills95/onvif-protect-bridge/general)

## The Problem

UniFi Protect won't add cameras unless they respond to ONVIF discovery and serve compliant SOAP endpoints. It also deduplicates cameras by MAC address — so you can't fake multiple cameras from a single host using IP aliases.

## How It Works

Each camera runs as its own Docker container with a unique MAC address via [macvlan networking](https://docs.docker.com/network/drivers/macvlan/). From Protect's perspective, each container is a real camera on the LAN.

Inside each container:
- **mediamtx** restreams the upstream RTSP source (e.g. from a DVR) on port 8554
- **ONVIF HTTP server** answers `GetCapabilities`, `GetProfiles`, `GetStreamUri`, etc.
- **WS-Discovery** (UDP 3702) responds to Protect's multicast probes so cameras appear automatically

## Requirements

- Docker with macvlan support (Linux host recommended — works on Raspberry Pi, any x86 server)
- Your server must be on the same LAN as the UniFi Cloud Key / Dream Machine running Protect
- Upstream RTSP streams (e.g. from a DVR or NVR)

> **Mac:** macvlan requires [OrbStack](https://orbstack.dev). Set `NETWORK_INTERFACE=en0`.

## Quick Start

**1. Clone and configure**

```bash
git clone https://github.com/eddwills95/onvif-protect-bridge.git
cd onvif-protect-bridge
cp .env.template .env
```

Edit `.env` with your RTSP URLs and network interface:

```env
NETWORK_INTERFACE=eth0          # your server's physical NIC (eno1, eth0, etc.)
CAM1_RTSP_URL=rtsp://admin:password@192.168.1.x:554/stream?channel=1
CAM2_RTSP_URL=rtsp://admin:password@192.168.1.x:554/stream?channel=2
# ... add as many as you need
```

**2. Set camera display names**

Open `docker-compose.yml` and update the `CAMERA_NAME` value for each service to match your camera locations (e.g. `Front Door`, `Garage`). This is the name that appears in Protect.

**3. Deploy**

```bash
docker compose up -d
```

Protect will auto-discover the cameras via WS-Discovery within a minute. If they don't appear automatically, go to **Protect → Cameras → Add**.

## Adding or Removing Cameras

Copy an existing service block in `docker-compose.yml`, assign a new `ipv4_address` on your LAN subnet, a unique `mac_address` (see note below), and add the corresponding `CAM{n}_RTSP_URL` to `.env`. Redeploy with `docker compose up -d`.

> **Why `mac_address` is pinned:** Docker's macvlan driver assigns a new random MAC address to a container every time it's recreated (image update, config change, host reboot). UniFi Protect identifies physical devices by MAC address, so without a pinned `mac_address`, every container recreate makes Protect see what looks like new hardware — causing repeated re-adoption prompts and duplicate camera entries. Pinning a fixed `mac_address` per service keeps each camera's identity stable indefinitely. Use any locally-administered MAC (second hex digit of the first byte — `2`, `6`, `a`, or `e` — keeps it out of real vendor ranges) that's unique across your services.

## Deploying with Portainer

If you manage Docker via Portainer, you can deploy as a Stack without SSH access.

**1. Create the stack**

Go to **Portainer → Stacks → Add stack**. Give it a name (e.g. `onvif-protect-bridge`), then paste the contents of `docker-compose.yml` into the Web editor.

Update the `CAMERA_NAME` values in the editor to match your camera locations before deploying.

**2. Set environment variables**

Scroll down to the **Environment variables** section and add:

| Name | Example value |
|---|---|
| `NETWORK_INTERFACE` | `eth0` |
| `CAM1_RTSP_URL` | `rtsp://admin:password@192.168.1.x:554/stream?channel=1` |
| `CAM2_RTSP_URL` | `rtsp://admin:password@192.168.1.x:554/stream?channel=2` |
| `CAM3_RTSP_URL` | `rtsp://admin:password@192.168.1.x:554/stream?channel=3` |

Add one row per camera.

**3. Deploy**

Click **Deploy the stack**. Portainer will pull `eddwills95/onvif-protect-bridge:latest` and start each container on its macvlan IP.

> To add a camera later: edit the stack (Stacks → your stack → Editor), add the new service block and environment variable, then click **Update the stack**.

## Environment Variables

| Variable | Set in | Description |
|---|---|---|
| `NETWORK_INTERFACE` | `.env` | macvlan parent interface (e.g. `eth0`, `eno1`) |
| `CAM{n}_RTSP_URL` | `.env` | Upstream RTSP URL for camera n |
| `CAMERA_ID` | `docker-compose.yml` | Unique ID per container (e.g. `cam1`) |
| `CAMERA_NAME` | `docker-compose.yml` | Display name shown in Protect (e.g. `Patio`) |
| `CAMERA_RTSP_URL` | `docker-compose.yml` | Mirrors `CAM{n}_RTSP_URL` for the container |
| `CAMERA_PORT` | `docker-compose.yml` | ONVIF HTTP port (default `8080`) |
| `CAMERA_UUID` | `docker-compose.yml` | Optional. Overrides the ONVIF device UUID, which is otherwise derived deterministically from `CAMERA_ID`. Only set this to preserve the identity of a camera whose `CAMERA_ID` you need to change. |
| `RTSP_STREAM_PORT` | `docker-compose.yml` | mediamtx RTSP output port (default `8554`) |
| `DEBUG` | `docker-compose.yml` | Optional. Set to log every incoming SOAP request body — off by default to keep the request path fast and logs quiet. |

## Supported ONVIF Actions

- `GetSystemDateAndTime`
- `GetCapabilities` / `GetServices` / `GetScopes`
- `GetDeviceInformation`
- `GetUsers`
- `GetProfiles` / `GetVideoSources`
- `GetStreamUri`
- `GetSnapshotUri`

## Contributing

PRs welcome. The architecture is documented in [CLAUDE.md](CLAUDE.md) — in particular the "Adding a New ONVIF Action" section walks through exactly what to change when extending the ONVIF surface.

### Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org). Your commit message prefix determines what happens when your PR is merged:

| Prefix | Example | Release |
|---|---|---|
| `fix:` | `fix: correct GetStreamUri port` | Patch — `1.0.1` |
| `feat:` | `feat: add GetSnapshotUri proxy` | Minor — `1.1.0` |
| `feat!:` or `BREAKING CHANGE:` | `feat!: change config format` | Major — `2.0.0` |
| `chore:`, `docs:`, `refactor:` | `chore: update readme` | No release |

### Release process

Releases are fully automated. When a PR is merged to `main`, [semantic-release](https://semantic-release.gitbook.io) analyses the commits and — if there's a releasable change — creates a git tag and GitHub Release with a generated changelog. The Docker image is then built and pushed automatically with matching semver tags (`1.2.0`, `1.2`, `1`, `latest`).

## License

MIT
