import { beforeAll, describe, expect, it } from "vitest";

const BASE_URL = "http://localhost:8080";

async function soapRequest(endpoint: string, body: string) {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/soap+xml" },
    body: `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    ${body}
  </s:Body>
</s:Envelope>`,
  });
  return response.text();
}

describe("ONVIF Server Integration Tests", () => {
  beforeAll(async () => {
    try {
      await fetch(`${BASE_URL}/health`);
    } catch {
      throw new Error(
        "Server is not running. Start with 'npm run dev' before running tests."
      );
    }
  });

  describe("Health Check", () => {
    it("should return health status with cameras array", async () => {
      const response = await fetch(`${BASE_URL}/health`);
      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data).toMatchObject({
        status: "ok",
        cameras: expect.arrayContaining([
          expect.objectContaining({
            id: expect.any(String),
            name: expect.any(String),
          }),
        ]),
        config: {
          onvifPort: expect.any(Number),
          rtspPort: expect.any(Number),
          host: expect.any(String),
        },
      });
    });
  });

  describe("Device Service", () => {
    it("should handle GetSystemDateAndTime", async () => {
      const response = await soapRequest(
        "/onvif/device_service",
        '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
      );

      expect(response).toContain("GetSystemDateAndTimeResponse");
      expect(response).toContain("<UTCDateTime>");
      expect(response).toContain("<Hour>");
      expect(response).toContain("<Year>");
    });

    it("should handle GetDeviceInformation", async () => {
      const response = await soapRequest(
        "/onvif/device_service",
        '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
      );

      expect(response).toContain("GetDeviceInformationResponse");
      expect(response).toContain("<Manufacturer>RTSP Bridge</Manufacturer>");
    });

    it("should handle GetServices", async () => {
      const response = await soapRequest(
        "/onvif/device_service",
        `<GetServices xmlns="http://www.onvif.org/ver10/device/wsdl">
          <IncludeCapability>true</IncludeCapability>
        </GetServices>`
      );

      expect(response).toContain("GetServicesResponse");
      expect(response).toContain("/onvif/media_service</XAddr>");
      expect(response).toContain("<RTP_TCP>true</RTP_TCP>");
    });
  });

  describe("Media Service", () => {
    it("should handle GetProfiles and return all cameras", async () => {
      const response = await soapRequest(
        "/onvif/media_service",
        '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
      );

      expect(response).toContain("GetProfilesResponse");
      expect(response).toContain('<Profiles token="profile_');
      expect(response).toContain("<Encoding>H264</Encoding>");
    });

    it("should handle GetStreamUri", async () => {
      const response = await soapRequest(
        "/onvif/media_service",
        `<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">
          <ProfileToken>profile_cam1</ProfileToken>
          <Protocol>RTSP</Protocol>
        </GetStreamUri>`
      );

      expect(response).toContain("GetStreamUriResponse");
      expect(response).toContain("<Uri>rtsp://");
      expect(response).toContain("<InvalidAfterConnect>false</InvalidAfterConnect>");
    });
  });

  describe("Error Handling", () => {
    it("should reject requests without SOAP action", async () => {
      const response = await fetch(`${BASE_URL}/onvif/device_service`, {
        method: "POST",
        headers: { "Content-Type": "application/soap+xml" },
        body: "invalid soap",
      });

      expect(response.status).toBe(400);
      expect(await response.text()).toContain("Invalid SOAP request");
    });

    it("should reject unsupported actions", async () => {
      const response = await soapRequest(
        "/onvif/device_service",
        '<UnsupportedAction xmlns="http://www.onvif.org/ver10/device/wsdl"/>'
      );

      expect(response).toContain("Unsupported Device action");
    });
  });
});
