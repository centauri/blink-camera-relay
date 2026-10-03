# Source provenance and local changes

Upstream revisions inspected 2026-10-02. Local adaptations are maintained in this repository.

| Component | Source/version | Treatment |
|---|---|---|
| BlinkPy | [fronzbot/blinkpy](https://github.com/fronzbot/blinkpy/tree/c36646ea0c838db04f48ea10a8cae2493dbb8cc6), dev commit `c36646ea0c838db04f48ea10a8cae2493dbb8cc6` | Source vendored under `vendor/blinkpy`, MIT license preserved. Uses OAuth v2 and `camera.init_livestream()`. |
| ONVIF bridge | [EddWills95/onvif-protect-bridge](https://github.com/EddWills95/onvif-protect-bridge/tree/84eb306f39978a83d3d60ee3ed63dfacd51a603e), commit `84eb306f39978a83d3d60ee3ed63dfacd51a603e` | Source vendored under `vendor/onvif`, local changes listed below. Upstream README declares MIT; the fetched tree contains no separate LICENSE file. Preserve upstream attribution when redistributing. |
| MediaMTX | [bluenviron/mediamtx v1.21.1](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.1) | Pinned Docker tag, standalone binary used in local tests. |
| FFmpeg | Debian bookworm package in Docker; imageio-ffmpeg bundled binary in Windows tests | No executable tools are committed to Git. Container images include Debian FFmpeg; corresponding Debian sources are distributed in the matching sources image. |

BlinkPy's current source uses `read(9)` and `read(payload_length)`, which do not guarantee whole TCP frames. Open upstream PRs [#1232](https://github.com/fronzbot/blinkpy/pull/1232), [#1303](https://github.com/fronzbot/blinkpy/pull/1303) and [#1304](https://github.com/fronzbot/blinkpy/pull/1304) address related streaming work. This POC does not install an unmerged PR wholesale.

`bridge/immis.py` subclasses the pinned upstream class, preserving its authentication header, keepalive and command-polling behavior. Local changes: readexactly framing, bounded frame size/read time, FFmpeg-client readiness before forwarding, cancellation of sibling tasks, and verified TLS instead of upstream's disabled certificate verification.

Local ONVIF changes: pin MediaMTX, use Node 22, explicit multicast LAN interface, terminate on embedded MediaMTX failure, external-MediaMTX test mode, stable configured MAC reporting, namespace-tolerant SOAP action parsing, 720p/15fps H.264 profile matching the encoder, consistent source token, honest unsupported-snapshot response, and corrected unsupported authentication claims. The original upstream tests are retained as reference, but some expectations describe its older configuration/profile and are not the validation contract for this adaptation.

This is an experimental live-video adapter, not an ONVIF conformance certification or a guarantee of Protect compatibility. See the test report for what was actually exercised.

Additional integration fixes: well-formed SOAP envelopes and namespace-qualified fields for scopes, services, clock and capabilities; separate device/media service advertisements; URI-encoded discovery names; a test-only discovery port setting; and an explicit MediaMTX configuration with source settings in `pathDefaults`, on-demand restreaming and unused MoQ listeners disabled.


## Distribution scope

The root MIT grant applies only to original bridge/dashboard code. BlinkPy's
original MIT copyright/license is retained verbatim. ONVIF upstream declares
MIT in its README, but has no standalone license at the pinned commit; the
added vendor/onvif/LICENSE records that limitation and preserves attribution.
MediaMTX's MIT license is included with the ONVIF image. NPM and Python package
license metadata remains in installed packages; SBOMs enumerate dependencies.

FFmpeg with Debian's x264 support includes GPL components. It runs as a separate
executable; the root MIT license does not relicense FFmpeg or its dependencies.
Matching Debian source-package archives and package notices are delivered in
companion sources images before runtime publication. The inherited Python and
Node runtime distributions retain their own licenses. This inventory is not a
legal opinion or a claim of trademark/ONVIF certification.

Release preparation removed unused semantic-release dependencies, updated the ONVIF npm lockfile with npm audit fix (zero reported vulnerabilities), switched its base to Debian for matching source-package collection, and added license notices.
