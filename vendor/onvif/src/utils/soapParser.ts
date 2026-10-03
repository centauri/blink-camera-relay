export function extractSoapAction(body: string): string | null {
  // Try to extract from SOAP body tag
  const bodyMatch = body.match(/<(?:[\w.-]+:)?Body\b[^>]*>(.*?)<\/(?:[\w.-]+:)?Body>/s);
  if (!bodyMatch) return null;

  // Extract the first tag inside Body
  const actionMatch = bodyMatch[1].match(/<(?:[\w.-]+:)?([\w.-]+)(?=[\s/>])/);
  return actionMatch ? actionMatch[1] : null;
}

export function hasSecurity(body: string): boolean {
  return body.includes("<Security");
}
