import { envelope } from "../../utils/envelope";

export function getUsers(): string {
  return envelope(`
<GetUsersResponse xmlns="http://www.onvif.org/ver10/device/wsdl">
  <User>
    <Username>admin</Username>
    <UserLevel>Administrator</UserLevel>
  </User>
</GetUsersResponse>`);
}
