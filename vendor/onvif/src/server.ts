import "dotenv/config";
import { spawn, type ChildProcess } from "node:child_process";
import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { WSDiscoveryServer } from "../ws-discovery";
import { DeviceController } from "./controllers/DeviceController";
import { MediaController } from "./controllers/MediaController";
import { Config } from "./config/Config";
import { loadCameraFromEnv } from "./config/CameraLoader";
import { createDeviceRoutes } from "./routes/device.routes";
import { createMediaRoutes } from "./routes/media.routes";

const config = new Config();
const camera = loadCameraFromEnv();

/* ---------------- MediaMTX ---------------- */

function startMediaMTX(): ChildProcess {
  const mtx = spawn("mediamtx", [], { cwd: process.cwd() });

  mtx.stdout.on("data", (d) => process.stdout.write(`[mediamtx] ${d}`));
  mtx.stderr.on("data", (d) => process.stderr.write(`[mediamtx] ${d}`));

  mtx.on("exit", (code, signal) => {
    if (signal !== "SIGTERM" && signal !== "SIGKILL") {
      console.error(`[mediamtx] exited unexpectedly (code=${code})`);
      process.exit(1);
    }
  });

  mtx.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "ENOENT") {
      console.error("[mediamtx] binary not found in PATH");
      process.exit(1);
    } else {
      console.error("[mediamtx] failed to start:", err.message);
    }
  });

  console.log("✅ MediaMTX started");
  return mtx;
}

// External mode allows the integration harness to own and clean up MediaMTX.
const mtx = process.env.MEDIAMTX_EXTERNAL === "1" ? null : startMediaMTX();

/* ---------------- ONVIF server ---------------- */

const app = new Hono();

app.use("*", async (c, next) => {
  console.log(`[${camera.id}] ${c.req.method} ${c.req.path}`);
  await next();
});

app.get("/health", (c) =>
  c.json({
    status: "ok",
    camera: { id: camera.id, name: camera.name },
    config: { onvifPort: camera.port, rtspPort: config.rtspStreamPort, host: config.hostIp },
  })
);

const deviceController = new DeviceController({
  host: camera.ip ?? config.hostIp,
  port: camera.port,
  cameraId: camera.id,
  cameraName: camera.name,
});

const mediaController = new MediaController({
  cameras: [camera],
  host: config.rtspHost,
  rtspPort: config.rtspStreamPort,
});

app.route("/onvif/device_service", createDeviceRoutes(deviceController));
app.route("/onvif/media_service", createMediaRoutes(mediaController));
app.get("*", (c) => c.text("GET unsupported by ONVIF implementation", 200));

const server = serve({ fetch: app.fetch, port: camera.port, hostname: "0.0.0.0" });
console.log(`✅ [${camera.name}] ONVIF listening on :${camera.port}`);
console.log(`   http://${config.hostIp}:${camera.port}/health`);

/* ---------------- WS-Discovery ---------------- */

const wsDiscovery = process.env.DISCOVERY_ENABLED === "false"
  ? null : new WSDiscoveryServer([camera], config.hostIp);
wsDiscovery?.start();
console.log(wsDiscovery ? "WS-Discovery enabled" : "WS-Discovery disabled; ONVIF remains available");

/* ---------------- Shutdown ---------------- */

const shutdown = () => {
  console.log("\n⚠️  Shutting down gracefully...");
  mtx?.kill("SIGTERM");
  wsDiscovery?.stop();
  server.close(() => {
    console.log("✅ Server closed");
    process.exit(0);
  });
  setTimeout(() => {
    console.error("❌ Forced shutdown after timeout");
    process.exit(1);
  }, 10000);
};

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
