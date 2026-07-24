#!/bin/sh
# Copy the locally-installed bobshell bundle into ./vendor/bobshell so the
# Docker image can ship the Bob CLI.
#
#   ./scripts/vendor-bob.sh && docker compose build
#
# bobshell is not on the public npm registry, so the image cannot install it.
# Only bundle/ is copied: bob.js is self-contained, and the package's optional
# node_modules (node-pty, canvas) are platform-native — a macOS build of those
# cannot load inside a linux container, and the CLI runs fine without them.
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dest="$repo_root/vendor/bobshell"

bob_bin=$(command -v bob || true)
if [ -z "$bob_bin" ]; then
    echo "bob is not on PATH. Install the bobshell npm package first." >&2
    exit 1
fi

# The PATH entry is an npm shim; resolve it to <pkg>/bundle/bob.js.
bundle_dir=$(dirname -- "$(readlink -f -- "$bob_bin" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$bob_bin")")
if [ ! -f "$bundle_dir/bob.js" ]; then
    echo "Resolved '$bob_bin' to '$bundle_dir', which has no bob.js." >&2
    exit 1
fi

rm -rf "$dest"
mkdir -p "$dest"
cp -R "$bundle_dir" "$dest/bundle"
echo "Vendored $("$bob_bin" --version 2>/dev/null || echo bobshell) -> vendor/bobshell/bundle"
