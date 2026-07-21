#!/bin/sh
# Install the pml CLI globally as an editable dev install (repo changes apply immediately).
set -eu
cd "$(dirname "$0")"
uv tool install --editable . --force
pml --help >/dev/null
echo "pml installed globally: $(command -v pml)"
