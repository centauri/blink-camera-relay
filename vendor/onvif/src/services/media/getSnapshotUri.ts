import { envelope } from "../../utils/envelope";
import { Camera } from "../../domain/Camera";
export function getSnapshotUri(cameras: Camera[], profileToken: string, host: string, rtspPort: number): string {
  return envelope(`<s:Fault xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:ter="http://www.onvif.org/ver10/error"><s:Code><s:Value>s:Receiver</s:Value><s:Subcode><s:Value>ter:ActionNotSupported</s:Value></s:Subcode></s:Code><s:Reason><s:Text xml:lang="en">Snapshot unavailable in this live-video POC</s:Text></s:Reason></s:Fault>`);
}
