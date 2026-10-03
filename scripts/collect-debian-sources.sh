#!/bin/sh
set -eu
# Preserve exact matching source archives (including Debian patches/build rules)
# for every installed Debian package, not only the ffmpeg executable.
mkdir -p /sources
sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources
apt-get update
apt-get install -y --no-install-recommends dpkg-dev ca-certificates
cd /sources
dpkg-query -W -f='${source:Package}=${source:Version}\n' | sort -u > packages.txt
while IFS= read -r package; do
  apt-get source --download-only "$package"
done < packages.txt
cp -a /usr/share/doc /sources/package-notices
sha256sum ./*.dsc ./*.tar.* ./*.diff.* 2>/dev/null > SHA256SUMS || test -s SHA256SUMS
