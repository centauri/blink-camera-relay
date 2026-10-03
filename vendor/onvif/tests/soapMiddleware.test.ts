import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Context } from "hono";
import { soapMiddleware } from "../src/middleware/soap.middleware";

const SOAP_BODY = `<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body><GetCapabilities/></s:Body>
</s:Envelope>`;

function fakeContext(body: string) {
  const vars = new Map<string, unknown>();
  return {
    req: { text: async () => body },
    set: (key: string, value: unknown) => vars.set(key, value),
    get: (key: string) => vars.get(key),
    text: (body: string, status: number) => ({ body, status }),
  } as unknown as Context;
}

const originalDebug = process.env.DEBUG;

beforeEach(() => {
  delete process.env.DEBUG;
});

afterEach(() => {
  if (originalDebug === undefined) delete process.env.DEBUG;
  else process.env.DEBUG = originalDebug;
  vi.restoreAllMocks();
});

describe("soapMiddleware request logging", () => {
  it("does not log the SOAP body when DEBUG is unset", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const c = fakeContext(SOAP_BODY);

    await soapMiddleware(c, async () => {});

    expect(logSpy).not.toHaveBeenCalled();
  });

  it("logs the SOAP body when DEBUG=true", async () => {
    process.env.DEBUG = "true";
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const c = fakeContext(SOAP_BODY);

    await soapMiddleware(c, async () => {});

    expect(logSpy).toHaveBeenCalledWith(SOAP_BODY);
  });
});
