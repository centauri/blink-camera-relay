import crypto from "crypto";

export interface CameraConfig {
  id: string;
  name: string;
  port: number;
  rtspUrl: string;
  ip?: string;
  uuid?: string;
}

// Fixed namespace for this project. Never change it — the device UUIDs derived
// from it are the identity Protect uses to recognise an already-adopted camera.
const UUID_NAMESPACE = "a1f4c2e0-6b3d-4f8a-9c17-2d5e8b0a7f31";

/**
 * RFC 4122 v5 (SHA-1, name-based) UUID.
 *
 * Deterministic: the same name always yields the same UUID, so a camera keeps
 * its ONVIF identity across container restarts, redeploys and image updates.
 */
function uuidV5(name: string, namespace: string): string {
  const namespaceBytes = Buffer.from(namespace.replace(/-/g, ""), "hex");
  const hash = crypto
    .createHash("sha1")
    .update(namespaceBytes)
    .update(name, "utf8")
    .digest();

  const bytes = hash.subarray(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50; // version 5
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant

  const hex = bytes.toString("hex");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
}

export class Camera {
  readonly id: string;
  readonly name: string;
  readonly port: number;
  readonly rtspUrl: string;
  readonly ip: string | undefined;
  readonly deviceUuid: string;

  constructor(config: CameraConfig) {
    this.id = config.id;
    this.name = config.name;
    this.port = config.port;
    this.rtspUrl = config.rtspUrl;
    this.ip = config.ip;
    this.deviceUuid = config.uuid ?? uuidV5(config.id, UUID_NAMESPACE);

    console.log(`Camera initialized: ${this.name} (${this.ip ?? "shared IP"}:${this.port}, UUID: ${this.deviceUuid})`);
  }

  get profileToken() {
    return `profile_${this.id}`;
  }

  // Returns the MediaMTX restream URL that Protect connects to
  rtspUri(host: string, rtspPort: number) {
    return `rtsp://${host}:${rtspPort}/${this.id}`;
  }
}
