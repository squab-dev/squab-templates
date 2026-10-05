#!/bin/sh
set -eu
python3 tools/smoke-hytale.py "${1:-squab-hytale:verify-amd64}"
