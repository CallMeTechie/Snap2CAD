#!/bin/sh
# Kopiert three.js und IBM-Plex-Schriften aus node_modules nach static/vendor.
# Aufruf im Verzeichnis web/:  npm install --omit=dev && sh scripts/vendor.sh
set -eu
NM=node_modules
OUT=static/vendor
rm -rf "$OUT"
mkdir -p "$OUT/three" "$OUT/fonts"
cp "$NM/three/build/three.module.min.js" "$OUT/three/three.module.js"
for f in controls/OrbitControls.js loaders/STLLoader.js; do
  # Bare-Import 'three' auf relativen Pfad umschreiben (keine Import-Map noetig, CSP bleibt strikt)
  sed "s#from 'three'#from './three.module.js'#g" "$NM/three/examples/jsm/$f" > "$OUT/three/$(basename "$f")"
done
cp "$NM/three/LICENSE" "$OUT/three/LICENSE"
for w in 400 500 600 700; do
  cp "$NM/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-$w-normal.woff2" "$OUT/fonts/"
done
for w in 400 500 600; do
  cp "$NM/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-$w-normal.woff2" "$OUT/fonts/"
done
cp "$NM/@fontsource/ibm-plex-sans/LICENSE" "$OUT/fonts/LICENSE" 2>/dev/null || true
echo "vendor: fertig"
ls -la "$OUT/three" "$OUT/fonts"
