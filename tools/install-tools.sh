#!/bin/sh
set -eu
mkdir -p .tools/bin
fetch() {
    name=$1 version=$2 checksum=$3
    archive="${name}_${version}_linux_amd64.tar.gz"
    curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
      "https://github.com/chainguard-dev/$name/releases/download/v$version/$archive" -o ".tools/$archive"
    printf '%s  %s\n' "$checksum" ".tools/$archive" | sha256sum -c -
    tar -xzf ".tools/$archive" -C .tools
    cp ".tools/${name}_${version}_linux_amd64/$name" ".tools/bin/$name"
}
fetch apko 1.4.1 d72352a2a875440946c05877a2e20eb4ffe6ab785cea8e5dbea942f1d62fd42e
fetch melange 0.60.0 90396912ef4a1b7243ba8765080d408754497e5c14e14132c32461fdcd54e606
