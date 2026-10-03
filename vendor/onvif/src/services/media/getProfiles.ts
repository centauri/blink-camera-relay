import { envelope } from "../../utils/envelope";
import { Camera } from "../../domain/Camera";

export function getProfiles(cameras: Camera[]): string {
  return envelope(`<GetProfilesResponse xmlns="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">${cameras.map(camera => `
  <Profiles token="${camera.profileToken}" fixed="true">
    <tt:Name>${camera.name}</tt:Name>
    <tt:VideoSourceConfiguration token="vsc_${camera.id}">
      <tt:Name>Live video</tt:Name><tt:UseCount>1</tt:UseCount>
      <tt:SourceToken>vs_1</tt:SourceToken>
      <tt:Bounds x="0" y="0" width="1280" height="720"/>
    </tt:VideoSourceConfiguration>
    <tt:VideoEncoderConfiguration token="vec_${camera.id}">
      <tt:Name>H264 720p</tt:Name><tt:UseCount>1</tt:UseCount>
      <tt:Encoding>H264</tt:Encoding>
      <tt:Resolution><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution>
      <tt:Quality>5</tt:Quality>
      <tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>2048</tt:BitrateLimit></tt:RateControl>
      <tt:H264><tt:GovLength>30</tt:GovLength><tt:H264Profile>Baseline</tt:H264Profile></tt:H264>
      <tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>1</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>
      <tt:SessionTimeout>PT60S</tt:SessionTimeout>
    </tt:VideoEncoderConfiguration>
  </Profiles>`).join("")}</GetProfilesResponse>`);
}
