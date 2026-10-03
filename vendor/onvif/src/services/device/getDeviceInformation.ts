import { envelope } from "../../utils/envelope";

export function getDeviceInformation(cameraId: string, cameraName: string): string {
  return envelope(`
<GetDeviceInformationResponse xmlns="http://www.onvif.org/ver10/device/wsdl">
  <Manufacturer>RTSP Bridge</Manufacturer>
  <Model>${cameraName}</Model>
  <FirmwareVersion>1.0</FirmwareVersion>
  <SerialNumber>${cameraId}</SerialNumber>
  <HardwareId>${cameraId}</HardwareId>
</GetDeviceInformationResponse>`);
}
