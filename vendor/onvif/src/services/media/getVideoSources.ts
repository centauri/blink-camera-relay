import { envelope } from "../../utils/envelope";
export function getVideoSources(): string {
  return envelope(`<GetVideoSourcesResponse xmlns="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><VideoSources token="vs_1"><tt:Framerate>15</tt:Framerate><tt:Resolution><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution></VideoSources></GetVideoSourcesResponse>`);
}
