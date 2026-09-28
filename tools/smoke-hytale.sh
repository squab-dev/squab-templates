#!/bin/sh
set -eu
engine=${CONTAINER_ENGINE:-docker}
image=${1:-squab-hytale:verify-amd64}
[ "$("$engine" run --rm --entrypoint /bin/id "$image" -u)" = 65532 ]
"$engine" run --rm --entrypoint java "$image" -version
set +e
"$engine" run --rm "$image"
code=$?
set -e
[ "$code" = 64 ] || { echo "missing checksums should exit 64, got $code"; exit 1; }
"$engine" run --rm --entrypoint /bin/sh "$image" -c \
 'test -x /usr/local/bin/squab-hytale-launcher; test -w /data; test ! -e /squab-runtime; test "$HOME" = /data'
