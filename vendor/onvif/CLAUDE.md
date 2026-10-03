# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

`rtsp-2-protect` is an ONVIF bridge that makes RTSP camera streams appear as ONVIF-compliant IP cameras to UniFi Protect. Each camera runs as its own Docker container with a unique MAC address (via macvlan), so Protect sees them as genuine separate devices.

Each container:
- Runs **mediamtx** internally to restream the upstream RTSP source
- Exposes an **ONVIF HTTP server** (Hono) at `/onvif/device_service` and `/onvif/media_service`
- Exposes a **WS-Discovery** UDP server (port 3702) so Protect can auto-discover the camera

## Running

```bash
# Deploy via Docker Compose (production / Portainer)
docker compose up

# Run tests (integration — requires a running container)
npm test
```

> Tests in `tests/onvif.test.ts` make real HTTP requests. Point them at a running container by setting `CAMERA_PORT` in `.env`.

## Configuration

Copy `.env.template` to `.env` and fill in your RTSP URLs. Each camera is a separate container entry in `docker-compose.yml`.

### Environment Variables (per container)

| Variable | Default | Notes |
|---|---|---|
| `CAMERA_ID` | — | Required. Unique ID, e.g. `cam1`. Sets the ONVIF path and mediamtx stream name. |
| `CAMERA_NAME` | — | Required. Display name shown in Protect, e.g. `Patio`. |
| `CAMERA_RTSP_URL` | — | Required. Full RTSP URL of the upstream source camera. |
| `MTX_PATHS_<ID>_SOURCE` | — | Same value as `CAMERA_RTSP_URL`. Tells mediamtx where to pull from. |
| `CAMERA_PORT` | `8080` | ONVIF HTTP port. Must match the container's macvlan-assigned port. |
| `RTSP_STREAM_PORT` | `8554` | mediamtx RTSP output port. |
| `NETWORK_INTERFACE` | `eth0` | macvlan parent interface (`eth0` on Linux/Pi, `en0` on Mac via OrbStack). |

## Architecture

```
src/
  server.ts            — entry: loads camera from env, starts mediamtx, serves ONVIF + WS-Discovery
  config/
    Config.ts          — reads global env vars (RTSP_STREAM_PORT, HOST_IP)
    CameraLoader.ts    — loads a single Camera from env vars
  domain/Camera.ts     — value object: id, name, rtspUrl, port, UUID; rtspUri() → mediamtx path
  middleware/
    soap.middleware.ts — extracts SOAP action name from body; stores action+body in Hono ctx
  routes/
    device.routes.ts   — POST /onvif/device_service → DeviceController
    media.routes.ts    — POST /onvif/media_service  → MediaController
  controllers/
    DeviceController   — dispatches action string → device service functions
    MediaController    — dispatches action string → media service functions; holds Camera instance
  services/
    device/            — one file per ONVIF device action (GetCapabilities, GetServices, …)
    media/             — one file per ONVIF media action (GetProfiles, GetStreamUri, …)
  utils/
    envelope.ts        — wraps XML in a SOAP envelope
    soapParser.ts      — extracts action name from SOAP body
    getLocalIPv4.ts    — auto-detects LAN IP when HOST_IP is not set
ws-discovery.ts        — UDP multicast listener; answers WS-Discovery Probe with a ProbeMatch
```

### Adding a New ONVIF Action

1. Create `src/services/{device|media}/getMyAction.ts` — export a function returning a SOAP XML string (use `envelope()` from `utils/envelope.ts`).
2. Add the action name to the `*Action` union type in the relevant controller.
3. Add a `case "MyAction":` branch in the controller's `handle()` switch.
4. Add an integration test in `tests/onvif.test.ts`.

### SOAP Flow

Every ONVIF request is a `POST` with a SOAP envelope. `soapMiddleware` parses the action name from `<s:Body>` and stores it in Hono context variables (`soapAction`, `soapBody`). The controller reads `soapAction` and dispatches to the appropriate service function. Responses use `Content-Type: application/soap+xml`.

### XAddr URLs and Protect Compatibility

The `XAddr` fields in `GetCapabilities` and `GetServices` responses must exactly match the server's endpoint. In Docker mode the container's own macvlan IP is used (e.g. `http://192.168.1.101:8080/onvif/device_service`). The WS-Discovery `ProbeMatch` `XAddrs` must also match — this is how Protect knows where to send subsequent requests.
