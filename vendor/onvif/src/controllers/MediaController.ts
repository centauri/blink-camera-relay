import { Context } from "hono";
import { Camera } from "../domain/Camera";
import { getProfiles } from "../services/media/getProfiles";
import { getVideoSources } from "../services/media/getVideoSources";
import { getStreamUri } from "../services/media/getStreamUri";
import { getSnapshotUri } from "../services/media/getSnapshotUri";

type MediaAction =
  | "GetProfiles"
  | "GetVideoSources"
  | "GetStreamUri"
  | "GetSnapshotUri";

interface MediaControllerParams {
  cameras: Camera[];
  host: string;
  rtspPort: number;
}

export class MediaController {
  constructor(private params: MediaControllerParams) {}

  handle(action: string, c: Context): Response | null {
    console.log(`Handling: ${action}`);

    switch (action as MediaAction) {
      case "GetProfiles":
        return this.getProfiles(c);
      case "GetVideoSources":
        return this.getVideoSources(c);
      case "GetStreamUri":
        return this.getStreamUri(c);
      case "GetSnapshotUri":
        return this.getSnapshotUri(c);
      default:
        return null;
    }
  }

  private soapResponse(c: Context, xml: string): Response {
    return c.body(xml, 200, {
      "Content-Type": "application/soap+xml",
    });
  }

  private profileTokenFromBody(c: Context): string {
    const body: string = c.get("soapBody") ?? "";
    const match = body.match(/<(?:[\w.-]+:)?ProfileToken[^>]*>([^<]+)<\/(?:[\w.-]+:)?ProfileToken>/);
    return match?.[1] ?? this.params.cameras[0].profileToken;
  }

  private getProfiles(c: Context): Response {
    return this.soapResponse(c, getProfiles(this.params.cameras));
  }

  private getVideoSources(c: Context): Response {
    return this.soapResponse(c, getVideoSources());
  }

  private getStreamUri(c: Context): Response {
    return this.soapResponse(
      c,
      getStreamUri(
        this.params.cameras,
        this.profileTokenFromBody(c),
        this.params.host,
        this.params.rtspPort
      )
    );
  }

  private getSnapshotUri(c: Context): Response {
    return this.soapResponse(
      c,
      getSnapshotUri(
        this.params.cameras,
        this.profileTokenFromBody(c),
        this.params.host,
        this.params.rtspPort
      )
    );
  }
}
