import { describe, expect, it } from "vitest";
import { Camera } from "../src/domain/Camera";

const base = {
  name: "Patio",
  port: 8080,
  rtspUrl: "rtsp://example.local:554/stream",
};

describe("Camera.deviceUuid", () => {
  it("is stable across instances with the same id", () => {
    const a = new Camera({ ...base, id: "cam1" });
    const b = new Camera({ ...base, id: "cam1" });

    expect(a.deviceUuid).toBe(b.deviceUuid);
  });

  it("differs between cameras with different ids", () => {
    const a = new Camera({ ...base, id: "cam1" });
    const b = new Camera({ ...base, id: "cam2" });

    expect(a.deviceUuid).not.toBe(b.deviceUuid);
  });

  it("does not change when other camera fields change", () => {
    const a = new Camera({ ...base, id: "cam1" });
    const b = new Camera({
      id: "cam1",
      name: "Renamed Patio",
      port: 9090,
      rtspUrl: "rtsp://somewhere-else.local:554/other",
    });

    expect(a.deviceUuid).toBe(b.deviceUuid);
  });

  it("is a valid RFC 4122 v5 UUID", () => {
    const camera = new Camera({ ...base, id: "cam1" });

    expect(camera.deviceUuid).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });

  it("uses an explicit uuid when one is supplied", () => {
    const explicit = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";
    const camera = new Camera({ ...base, id: "cam1", uuid: explicit });

    expect(camera.deviceUuid).toBe(explicit);
  });
});
