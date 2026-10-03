import { Camera } from "../domain/Camera";

function requireEnv(key: string): string {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required env var: ${key}`);
  return val;
}

export function loadCameraFromEnv(): Camera {
  
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(requireEnv("CAMERA_ID")))
    throw new Error("CAMERA_ID must be a lowercase RTSP path token");
  if (/[<>&"']/.test(requireEnv("CAMERA_NAME")))
    throw new Error("CAMERA_NAME cannot contain XML delimiters");
  return new Camera({
    id: requireEnv("CAMERA_ID"),
    name: requireEnv("CAMERA_NAME"),
    rtspUrl: requireEnv("CAMERA_RTSP_URL"),
    port: parseInt(process.env.CAMERA_PORT ?? "8080"),
    uuid: process.env.CAMERA_UUID,
  });
}
