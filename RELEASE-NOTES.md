# v0.1.3

Watch several cameras together in the new Multi-view tab (issue #1, PR #2).

- Select cameras and launch a combined local live view.
- Two cameras stack vertically; three show one above two; four use quadrants.
  Larger selections use a grid, and narrow screens stack the videos.
- Each camera has independent playback status and session-renewal retries.
- Stopping the view, switching dashboard tabs, or hiding the browser tab releases
  the players without stopping the bridge streams.

Start the camera streams in Monitor first. Multi-view reuses the local HLS
streams and opens no additional Blink live sessions. Blink renewal gaps still
apply, and viewing several streams increases browser CPU and network usage.

Automated tests and integrated container smoke tests passed for the feature.
An isolated Chrome demo verified selection, layout, retry status and cleanup;
simultaneous playback from physical cameras still needs field verification.

Update ghcr.io/centauri/blink-camera-relay:latest (or pin :v0.1.3), keep appdata,
and refresh the dashboard to load the new Multi-view tab.
