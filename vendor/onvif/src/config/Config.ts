import { getLocalIPv4 } from "../utils/getLocalIPv4";

export interface ConfigParams {
  camerasConfigPath: string;
  rtspStreamPort: number;
  hostIp: string;
}

export class Config {
  public readonly camerasConfigPath: string;
  public readonly rtspStreamPort: number;
  public readonly hostIp: string;
  public readonly rtspHost: string;

  constructor(params?: Partial<ConfigParams>) {
    this.camerasConfigPath =
      params?.camerasConfigPath ??
      process.env.CAMERAS_CONFIG ??
      "./cameras.yml";
    this.rtspStreamPort =
      params?.rtspStreamPort ?? this.parsePort("RTSP_STREAM_PORT", 8554);
    this.hostIp = params?.hostIp ?? process.env.HOST_IP ?? getLocalIPv4();
    this.rtspHost = process.env.RTSP_HOST ?? this.hostIp;

    this.validate();
    this.logConfig();
  }

  private parsePort(envVar: string, defaultPort: number): number {
    const value = process.env[envVar];
    if (!value) return defaultPort;
    const port = Number(value);
    if (isNaN(port)) {
      throw new Error(`Invalid ${envVar}: "${value}" is not a valid port number`);
    }
    return port;
  }

  private validate(): void {
    const errors: string[] = [];

    if (this.rtspStreamPort < 1 || this.rtspStreamPort > 65535) {
      errors.push(`RTSP_STREAM_PORT must be between 1-65535 (got ${this.rtspStreamPort})`);
    }

    if (!this.hostIp || this.hostIp.trim() === "") {
      errors.push("HOST_IP cannot be empty or undetectable");
    }

    if (errors.length > 0) {
      throw new Error(
        `Configuration validation failed:\n${errors.map((e) => `  - ${e}`).join("\n")}`
      );
    }
  }

  private logConfig(): void {
    console.log("=".repeat(50));
    console.log("📹 RTSP-2-Protect ONVIF Bridge");
    console.log("=".repeat(50));
    console.log(`Cameras config:     ${this.camerasConfigPath}`);
    console.log(`RTSP Stream Port:   ${this.rtspStreamPort}`);
    console.log(`Host IP:            ${this.hostIp}`);
    console.log("=".repeat(50));
  }
}
