"""Verify published tags using the media types accepted by older Unraid checkers."""
import json
import os
import re
import urllib.request

DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
ACCEPT = ("application/vnd.docker.distribution.manifest.list.v2+json," +
          DOCKER_MANIFEST + ",application/vnd.oci.image.index.v1+json")


def verify(repository, tags, revision, opener=urllib.request.urlopen):
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    base = "https://ghcr.io"
    with opener(base + "/token?service=ghcr.io&scope=repository:" + repository + ":pull") as response:
        token = json.load(response)["token"]
    headers = {"Authorization": "Bearer " + token, "Accept": ACCEPT}
    digests = set()
    for tag in tags:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
            raise ValueError("Invalid tag")
        url = base + "/v2/" + repository + "/manifests/" + tag
        with opener(urllib.request.Request(url, headers=headers, method="HEAD")) as response:
            digest = response.headers.get("Docker-Content-Digest", "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError("Registry did not return a valid update digest")
        with opener(urllib.request.Request(url, headers=headers)) as response:
            manifest = json.load(response)
            if response.headers.get("Docker-Content-Digest") != digest:
                raise ValueError("Tag changed during verification")
        if manifest.get("mediaType") != DOCKER_MANIFEST:
            raise ValueError("Expected a Docker schema 2 image manifest")
        config_digest = manifest["config"]["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest):
            raise ValueError("Invalid config digest")
        with opener(urllib.request.Request(base + "/v2/" + repository + "/blobs/" + config_digest, headers=headers)) as response:
            config = json.load(response)
        if config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != revision:
            raise ValueError("Published image does not match the release commit")
        digests.add(digest)
        print(tag + ": Unraid-compatible digest " + digest)
    if len(digests) != 1:
        raise ValueError("Published tags do not refer to the same image")


if __name__ == "__main__":
    revision = os.environ["GITHUB_SHA"]
    tags = [os.environ["IMAGE_CHANNEL"], "sha-" + revision]
    if os.environ.get("IMAGE_VERSION"):
        tags.append(os.environ["IMAGE_VERSION"])
    verify(os.environ["IMAGE_REPOSITORY"].lower(), tags, revision)
