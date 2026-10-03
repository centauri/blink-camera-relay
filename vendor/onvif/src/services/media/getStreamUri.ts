import { envelope } from "../../utils/envelope";
import { Camera } from "../../domain/Camera";

export function getStreamUri(
  cameras: Camera[],
  profileToken: string,
  host: string,
  rtspPort: number
): string {
  const camera =
    cameras.find((c) => c.profileToken === profileToken) ?? cameras[0];
  const rtspUri = camera.rtspUri(host, rtspPort);

  return envelope(`
<GetStreamUriResponse xmlns="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <MediaUri>
    <tt:Uri>${rtspUri}</tt:Uri>
    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
    <tt:Timeout>PT60S</tt:Timeout>
  </MediaUri>
</GetStreamUriResponse>`);
}
