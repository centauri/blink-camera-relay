import { Hono } from "hono";
import type { DeviceController } from "../controllers/DeviceController";
import { soapMiddleware } from "../middleware/soap.middleware";

type Variables = {
  soapAction: string;
  soapBody: string;
};

export function createDeviceRoutes(
  controller: DeviceController
): Hono<{ Variables: Variables }> {
  const router = new Hono<{ Variables: Variables }>();

  router.post("/", soapMiddleware, (c) => {
    const action = c.get("soapAction") as string;
    const response = controller.handle(action, c);

    if (!response) {
      return c.text(`Unsupported Device action: ${action}`, 500);
    }

    return response;
  });

  return router;
}
