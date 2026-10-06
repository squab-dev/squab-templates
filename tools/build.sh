#!/bin/sh
set -eu
image=${1:-paper}
# Any image directory with an apko configuration; names are plain lowercase slugs.
case "$image" in *[!a-z0-9-]*|-*|'') echo 'Unknown image' >&2; exit 64;; esac
[ -f "images/$image/apko.yaml" ] || { echo 'Unknown image' >&2; exit 64; }
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
python3 tools/merge-lock.py "images/$image/wolfi.lock.json" "$build/resolved.lock.json" "$build/image.lock.json" "squab-$image-launcher"
"$APKO" build "images/$image/apko.yaml" "squab-$image:verify" "$build/image.tar" \
  --lockfile "$build/image.lock.json" --repository-append "$build/packages" \
  --keyring-append "$build/build.rsa.pub" --build-date 2026-09-16T00:00:00Z --sbom-path "$build/sbom"
if [ -f "images/$image/runtime.Dockerfile" ]; then
  docker load -i "$build/image.tar"
  docker build --platform linux/amd64 --file "images/$image/runtime.Dockerfile" \
    --tag "squab-$image:verify-amd64" "images/$image"
  # The final game image is already loaded. Avoid a second multi-GB archive.
  rm "$build/image.tar"
fi
