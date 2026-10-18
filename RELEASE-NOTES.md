# v0.1.5

Fix image publication compatibility with older Unraid Docker update checkers.

The image now explicitly uses Docker schema 2 media types. Older Unraid versions
request Docker manifests but omit the single-image OCI media type; GHCR answered
those requests with 404 for previous releases, resulting in "not available".

A post-publication check now verifies the registry HEAD digest, Docker manifest,
release commit and matching tags using the older Unraid Accept header.

Keep the repository set to ghcr.io/centauri/blink-camera-relay:latest. After this
release is published, use Check for Updates on Unraid's Docker page. No appdata
or template changes are needed. Server-specific DNS or registry access failures
can still prevent update checks.
