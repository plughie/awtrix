#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_HOME:-/Users/duv/Library/Android/sdk}"
BUILD_TOOLS="$SDK/build-tools/35.0.0"
PLATFORM="$SDK/platforms/android-35/android.jar"
JAVA_HOME_PATH="${JAVA_HOME:-/Users/duv/Library/Application Support/JDownloader 2/.install4j/jre.bundle/Contents/Home}"
JAVA_BIN="$JAVA_HOME_PATH/bin/java"
ECJ="$ROOT/build/tools/ecj.jar"
export JAVA_HOME="$JAVA_HOME_PATH"
export PATH="$JAVA_HOME_PATH/bin:$PATH"

APP="$ROOT/app"
BUILD="$ROOT/build"

mkdir -p "$BUILD/classes" "$BUILD/dex" "$BUILD/gen" "$BUILD/tools"

if [[ ! -f "$ECJ" ]]; then
  echo "Missing $ECJ"
  echo "Download org.eclipse.jdt:ecj into build/tools/ecj.jar, or set up a JDK and replace the ecj command with javac."
  exit 1
fi

rm -rf "$BUILD/classes" "$BUILD/dex" "$BUILD/gen" "$BUILD/compiled.flata" \
  "$BUILD/unsigned.apk" "$BUILD/unaligned.apk" \
  "$BUILD/SendImageToAWTRIX-debug-unsigned.apk" "$BUILD/SendImageToAWTRIX-debug.apk"
mkdir -p "$BUILD/classes" "$BUILD/dex" "$BUILD/gen"

"$BUILD_TOOLS/aapt2" compile --dir "$APP/src/main/res" -o "$BUILD/compiled.flata"
"$BUILD_TOOLS/aapt2" link -I "$PLATFORM" --manifest "$APP/src/main/AndroidManifest.xml" --java "$BUILD/gen" -o "$BUILD/unsigned.apk" "$BUILD/compiled.flata"
mapfile -d '' JAVA_SOURCES < <(find "$APP/src/main/java" "$BUILD/gen" -name '*.java' -print0)
"$JAVA_BIN" -jar "$ECJ" -1.8 -bootclasspath "$PLATFORM" -classpath "$PLATFORM" -d "$BUILD/classes" "${JAVA_SOURCES[@]}"

mapfile -d '' CLASS_FILES < <(find "$BUILD/classes" -name '*.class' -print0)
"$BUILD_TOOLS/d8" --min-api 23 --lib "$PLATFORM" --output "$BUILD/dex" "${CLASS_FILES[@]}"

cp "$BUILD/unsigned.apk" "$BUILD/unaligned.apk"
(cd "$BUILD/dex" && zip -qr ../unaligned.apk classes.dex)
"$BUILD_TOOLS/zipalign" -f 4 "$BUILD/unaligned.apk" "$BUILD/SendImageToAWTRIX-debug-unsigned.apk"

KEYSTORE="$BUILD/debug.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  "$JAVA_HOME_PATH/bin/keytool" -genkeypair -v -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Android Debug,O=Android,C=US"
fi

"$BUILD_TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-pass pass:android --key-pass pass:android \
  --out "$BUILD/SendImageToAWTRIX-debug.apk" "$BUILD/SendImageToAWTRIX-debug-unsigned.apk"
"$BUILD_TOOLS/apksigner" verify --verbose "$BUILD/SendImageToAWTRIX-debug.apk"

cp "$BUILD/SendImageToAWTRIX-debug.apk" "$ROOT/../Send Image to AWTRIX Android.apk"
echo "$ROOT/../Send Image to AWTRIX Android.apk"
