import { envelope } from "../../utils/envelope";
export function getScopes(): string {
  const scopes = ["onvif://www.onvif.org/type/video_encoder", "onvif://www.onvif.org/Profile/Streaming", `onvif://www.onvif.org/name/${encodeURIComponent(process.env.CAMERA_NAME || "Blink PoC")}`];
  return envelope(`<GetScopesResponse xmlns="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">${scopes.map(scope => `<Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>${scope}</tt:ScopeItem></Scopes>`).join("")}</GetScopesResponse>`);
}
