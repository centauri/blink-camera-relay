import type { Context, Next } from "hono";
import { extractSoapAction, hasSecurity } from "../utils/soapParser";

export async function soapMiddleware(c: Context, next: Next) {
  const body = await c.req.text();
  if (process.env.DEBUG) {
    console.log(body);
    console.log(hasSecurity(body) ? "AUTH: yes" : "AUTH: no");
  }

  const action = extractSoapAction(body);
  if (!action) {
    return c.text("Invalid SOAP request - no action found", 400);
  }

  // Store action and body in context for controller to use
  c.set("soapAction", action);
  c.set("soapBody", body);

  await next();
}
