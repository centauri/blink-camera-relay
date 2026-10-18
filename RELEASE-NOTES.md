# v0.1.4

Open a camera-only viewing window for TVs and fullscreen monitors from Multi-view.

- Select cameras and click Open viewing window.
- Videos fill a black background without dashboard navigation or settings.
- A Fullscreen button fades after inactivity; double-click a camera to toggle fullscreen.
- The viewing window runs independently of the dashboard and retries stream renewals.
- Closing the window releases playback without stopping bridge streams.

Uses existing authenticated local HLS streams without additional Blink live sessions.
Start the streams in Monitor first. Browser settings may open a tab instead of a
separate window. Fullscreen support varies by browser; browser fullscreen can also
be used. Blink renewal gaps still apply.

Update ghcr.io/centauri/blink-camera-relay:latest (or pin :v0.1.4), retain appdata,
and refresh the dashboard. The release Source code ZIP contains the matching source.
