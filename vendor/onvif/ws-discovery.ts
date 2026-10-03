import crypto from "crypto";
import dgram from "dgram";
import type { Camera } from "./src/domain/Camera";

export class WSDiscoveryServer {
  private socket: dgram.Socket;
  private readonly sendSockets: Map<string, dgram.Socket> = new Map();
  private readonly cameras: Camera[];
  private readonly multicastAddr = "239.255.255.250";
  private readonly discoveryPort = Number(process.env.DISCOVERY_PORT || "3702");
  private readonly hostIp: string;

  constructor(cameras: Camera[], hostIp: string) {
    this.cameras = cameras;
    this.hostIp = hostIp;
    this.socket = dgram.createSocket({ type: "udp4", reuseAddr: true });

    for (const cam of cameras) {
      if (cam.ip) {
        const sock = dgram.createSocket({ type: "udp4" });
        sock.on("error", (err) => console.warn(`[ws-discovery] send socket error for ${cam.id}: ${err.message}`));
        sock.bind(0, cam.ip);
        this.sendSockets.set(cam.id, sock);
      }
    }

    this.setupHandlers();
  }

  private setupHandlers(): void {
    this.socket.on("listening", () => {
      try {
        this.socket.addMembership(this.multicastAddr, this.hostIp);
        this.socket.setMulticastInterface(this.hostIp);
        console.log(`WS-Discovery listening on ${this.multicastAddr}:${this.discoveryPort}`);
        this.cameras.forEach((cam) =>
          console.log(`  ${cam.name}: http://${cam.ip ?? this.hostIp}:${cam.port}/onvif/device_service`)
        );
      } catch (err) {
        console.error("Failed to setup multicast:", err);
        console.log("WS-Discovery will continue without multicast (manual camera config required)");
      }
    });

    this.socket.on("message", (msg, rinfo) => this.handleProbe(msg, rinfo));
    this.socket.on("error", (err) => console.error("WS-Discovery socket error:", err));
  }

  private handleProbe(msg: Buffer, rinfo: dgram.RemoteInfo): void {
    const xml = msg.toString();

    if (!xml.includes("Probe")) return;

    console.log(`Probe received from ${rinfo.address}`);

    const messageIdMatch = xml.match(/<[^:>]+:MessageID[^>]*>([^<]+)<\/[^:>]+:MessageID>/);
    if (!messageIdMatch) {
      console.warn("Probe without MessageID, ignoring");
      return;
    }

    for (const cam of this.cameras) {
      const response = this.buildProbeResponse(messageIdMatch[1], cam);
      const sock = this.sendSockets.get(cam.id) ?? this.socket;
      sock.send(response, rinfo.port, rinfo.address);
    }
  }

  private buildProbeResponse(relatesTo: string, cam: Camera): string {
    return `<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:${crypto.randomUUID()}</w:MessageID>
    <w:RelatesTo>${relatesTo}</w:RelatesTo>
    <w:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</w:Action>
  </e:Header>
  <e:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <w:EndpointReference>
          <w:Address>urn:uuid:${cam.deviceUuid}</w:Address>
        </w:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/name/${encodeURIComponent(cam.name)} onvif://www.onvif.org/Profile/Streaming</d:Scopes>
        <d:XAddrs>http://${cam.ip ?? this.hostIp}:${cam.port}/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </e:Body>
</e:Envelope>`;
  }

  start(): void {
    console.log(`Starting WS-Discovery for ${this.cameras.length} camera(s): ${this.cameras.map((c) => c.name).join(", ")}`);
    this.socket.bind(this.discoveryPort);
  }

  stop(): void {
    console.log("Stopping WS-Discovery");
    this.socket.close();
    for (const sock of this.sendSockets.values()) sock.close();
  }
}
