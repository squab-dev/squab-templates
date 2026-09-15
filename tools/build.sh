#!/bin/sh
set -eu
image=${1:-paper}
[ "$image" = paper ] || { echo 'Unknown image' >&2; exit 64; }
APKO=${APKO:-apko}
MELANGE=${MELANGE:-melange}
build="build/$image"
mkdir -p "$build/sbom"
# A local, ephemeral APK signing key. Never committed or uploaded.
[ -f "$build/build.rsa" ] || "$MELANGE" keygen "$build/build.rsa"
"$MELANGE" build "images/$image/melange.yaml" --arch x86_64 \
  --runner bubblewrap --source-dir "images/$image" --out-dir "$build/packages" \
  --signing-key "$build/build.rsa" --build-date 2026-09-16T00:00:00Z
"$APKO" lock "images/$image/apko.yaml" --repository-append "$build/packages" \
  --keyring-append "$build/build.rsa.pub" --output "$build/resolved.lock.json"
python3 tools/merge-lock.py "images/$image/wolfi.lock.json" "$build/resolved.lock.json" "$build/image.lock.json"
"$APKO" build "images/$image/apko.yaml" "squab-$image:verify" "$build/image.tar" \
  --lockfile "$build/image.lock.json" --repository-append "$build/packages" \
  --keyring-append "$build/build.rsa.pub" --build-date 2026-09-16T00:00:00Z --sbom-path "$build/sbom"
