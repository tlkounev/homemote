#!/bin/sh
# Spuštění bez vlastního Docker image (čistý python image + kód ve sdílené složce).
# Při prvním startu stáhne závislosti a adb do /data, další starty jsou okamžité.
set -e
DATA_DIR="${DATA_DIR:-/data}"
DEPS="$DATA_DIR/pydeps"
REQ="/srv/requirements.txt"

if [ ! -f "$DEPS/.req" ] || ! cmp -s "$REQ" "$DEPS/.req"; then
  echo "Instaluji Python závislosti do $DEPS ..."
  rm -rf "$DEPS"
  pip install --no-cache-dir --disable-pip-version-check -q --target "$DEPS" -r "$REQ"
  cp "$REQ" "$DEPS/.req"
fi

if [ ! -x "$DATA_DIR/platform-tools/adb" ]; then
  echo "Stahuji Android platform-tools (adb) ..."
  python - "$DATA_DIR" <<'EOF'
import io, sys, urllib.request, zipfile
url = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=120).read())).extractall(sys.argv[1])
EOF
  chmod +x "$DATA_DIR/platform-tools/adb"
fi

export PYTHONPATH="$DEPS"
export PATH="$DATA_DIR/platform-tools:$PATH"
export HOME="$DATA_DIR/home"
mkdir -p "$HOME"
cd /srv
exec python -m app.main
