import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { loadCameraFromEnv } from "../src/config/CameraLoader";

const original = { ...process.env };

beforeEach(() => {
  process.env.CAMERA_ID = "cam1";
  process.env.CAMERA_NAME = "Patio";
  process.env.CAMERA_RTSP_URL = "rtsp://example.local:554/stream";
  delete process.env.CAMERA_UUID;
});

afterEach(() => {
  process.env = { ...original };
});

describe("loadCameraFromEnv", () => {
  it("derives a stable uuid from CAMERA_ID across loads", () => {
    const a = loadCameraFromEnv();
    const b = loadCameraFromEnv();

    expect(a.deviceUuid).toBe(b.deviceUuid);
  });

  it("honours CAMERA_UUID when set", () => {
    process.env.CAMERA_UUID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";

    expect(loadCameraFromEnv().deviceUuid).toBe(
      "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    );
  });
});
