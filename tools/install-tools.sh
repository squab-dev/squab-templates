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
fetch apko 1.4.6 bbe51cce228b70aef68f436da4fc11b5d235b06f8fc1d4c35b39116b86895271
fetch melange 0.61.2 9a78ee4bd5bd166b5d358b49249e0e6f25e10efede51cf407262218d8a65d78e
