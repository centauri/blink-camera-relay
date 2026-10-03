import { envelope } from "../../utils/envelope";
export function getSystemDateAndTime(): string {
  const now = new Date();
  return envelope(`<GetSystemDateAndTimeResponse xmlns="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType><tt:DaylightSavings>false</tt:DaylightSavings><tt:UTCDateTime><tt:Time><tt:Hour>${now.getUTCHours()}</tt:Hour><tt:Minute>${now.getUTCMinutes()}</tt:Minute><tt:Second>${now.getUTCSeconds()}</tt:Second></tt:Time><tt:Date><tt:Year>${now.getUTCFullYear()}</tt:Year><tt:Month>${now.getUTCMonth()+1}</tt:Month><tt:Day>${now.getUTCDate()}</tt:Day></tt:Date></tt:UTCDateTime></SystemDateAndTime></GetSystemDateAndTimeResponse>`);
}
