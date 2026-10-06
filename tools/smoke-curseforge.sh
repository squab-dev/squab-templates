#!/bin/sh
# Image checks without network access or a CurseForge key. Real modpack boots:
# python3 tools/boot-curseforge.py (see images/curseforge/README.md).
set -eu
engine=${CONTAINER_ENGINE:-docker}
image=${1:-squab-curseforge:verify-amd64}
run() { "$engine" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges:true "$@"; }
[ "$(run --entrypoint /bin/id "$image" -u)" = 65532 ]
for java in java-1.8-openjdk java-17-openjdk java-21-openjdk java-25-openjdk; do
  run --entrypoint "/usr/lib/jvm/$java/bin/java" "$image" -version
done
expect() {
  wanted=$1; shift
  set +e
  run "$@" "$image" >/dev/null 2>&1
  code=$?
  set -e
  [ "$code" = "$wanted" ] || { echo "expected exit $wanted, got $code ($*)"; exit 1; }
}
# No trusted EULA signal, then no key file, then a key in the environment.
expect 64 -e CF_MODPACK=example
expect 64 -e SQUAB_SYSTEM_LICENSE_ACCEPTED=true -e CF_MODPACK=example
expect 64 -e SQUAB_SYSTEM_LICENSE_ACCEPTED=true -e CF_MODPACK=example -e CF_API_KEY=x
expect 64 -e SQUAB_SYSTEM_LICENSE_ACCEPTED=true -e CF_MODPACK=example -e JAVA_TOOL_OPTIONS=-Xmx1g
run --entrypoint /bin/sh "$image" -c \
  'test -x /usr/local/bin/squab-curseforge-launcher; test -w /data; test ! -e /run/squab/secrets'
