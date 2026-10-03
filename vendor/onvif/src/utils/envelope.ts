export function envelope(body: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    ${body}
  </s:Body>
</s:Envelope>`;
}
