#!/bin/sh
set -eu
engine=${CONTAINER_ENGINE:-docker}
image=${1:-squab-paper:verify-amd64}
[ "$("$engine" run --rm --entrypoint /bin/id "$image" -u)" = 65532 ]
"$engine" run --rm --entrypoint java "$image" -version
set +e
"$engine" run --rm "$image"
code=$?
set -e
[ "$code" = 64 ] || { echo "missing license should exit 64, got $code"; exit 1; }
set +e
"$engine" run --rm -e SQUAB_SYSTEM_LICENSE_ACCEPTED=true "$image"
code=$?
set -e
[ "$code" = 65 ] || { echo "missing artifact should exit 65, got $code"; exit 1; }
"$engine" run --rm --entrypoint /bin/sh "$image" -c \
  'test ! -e /squab-runtime; test -x /usr/local/bin/squab-paper-launcher; test -w /data'
