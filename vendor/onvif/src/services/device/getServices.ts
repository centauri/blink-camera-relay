import { envelope } from "../../utils/envelope";
export interface GetServicesParams { host: string; port: number; }
export function getServices({ host, port }: GetServicesParams): string {
  return envelope(`<GetServicesResponse xmlns="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">${["device", "media"].map(service => `<Service><Namespace>http://www.onvif.org/ver10/${service}/wsdl</Namespace><XAddr>http://${host}:${port}/onvif/${service}_service</XAddr><Version><tt:Major>2</tt:Major><tt:Minor>0</tt:Minor></Version></Service>`).join("")}</GetServicesResponse>`);
}
