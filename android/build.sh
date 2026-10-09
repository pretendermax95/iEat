#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TOOLCHAIN_DIR="${IEAT_TOOLCHAIN:-/workspace/android-toolchain}"
TOOLS_DIR="$TOOLCHAIN_DIR/build-tools/android-15"
PLATFORM_JAR="$TOOLCHAIN_DIR/platform/android-35-ext15/android.jar"
OUTPUT_DIR="${IEAT_APK_OUTPUT:-/workspace/artifacts}"
BUILD_DIR="$PWD/android/build"
mkdir -p "$BUILD_DIR/classes" "$BUILD_DIR/dex" "$BUILD_DIR/assets/web" "$OUTPUT_DIR"
python3 - <<'PY'
from pathlib import Path
import shutil, json, importlib.util, os, tempfile
root=Path.cwd();assets=root/'android/build/assets'
for folder in ['css','js','images']:
 shutil.copytree(root/folder,assets/'web'/folder,dirs_exist_ok=True)
shutil.copy(root/'index.html',assets/'web/index.html')
p=assets/'web/js/app.js';s=p.read_text()
s=s.replace("async function api(path,data){", "async function api(path,data){if(window.IEatNative){const r=JSON.parse(window.IEatNative.request(path,JSON.stringify(data||{})));if(!r.ok)throw Error(r.error||'Ошибка приложения');return r.data;}")
s=s.replace('Данные хранятся на сервере приложения.','Данные хранятся только на этом устройстве.')
s=s.replace('Аккаунт, контактные данные и заказы хранятся в SQLite на сервере. Пароли хранятся в виде хешей, сессия — в HttpOnly cookie.', 'Аккаунт, контактные данные и заказы хранятся в SQLite на этом устройстве. Пароли защищены PBKDF2. При удалении приложения данные удаляются. Удалите приложение, чтобы очистить все локальные данные.')
p.write_text(s)
p=assets/'web/index.html';p.write_text(p.read_text().replace('Заказы сохраняются в приложении,','Заказы сохраняются только на этом устройстве,'))
with tempfile.TemporaryDirectory() as temp:
 os.environ['IEAT_DB']=temp+'/catalog.sqlite3'
 spec=importlib.util.spec_from_file_location('ieat_catalog',root/'server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 (assets/'catalog.json').write_text(json.dumps({'dishes':m.DISHES,'restaurants':m.RESTAURANTS,'demo':True},ensure_ascii=False))
PY
chmod +x "$TOOLS_DIR/aapt2" "$TOOLS_DIR/zipalign"
"$TOOLS_DIR/aapt2" compile --dir android/res -o "$BUILD_DIR/resources.zip"
"$TOOLS_DIR/aapt2" link -o "$BUILD_DIR/base.apk" --manifest android/AndroidManifest.xml -I "$PLATFORM_JAR" -A "$BUILD_DIR/assets" "$BUILD_DIR/resources.zip"
java -jar "$TOOLCHAIN_DIR/ecj.jar" -8 -proc:none -bootclasspath "$PLATFORM_JAR" -d "$BUILD_DIR/classes" android/src/com/ieat/app/MainActivity.java
mapfile -t CLASS_FILES < <(find "$BUILD_DIR/classes" -name '*.class')
java -cp "$TOOLS_DIR/lib/d8.jar" com.android.tools.r8.D8 --lib "$PLATFORM_JAR" --min-api 26 --output "$BUILD_DIR/dex" "${CLASS_FILES[@]}"
cp "$BUILD_DIR/base.apk" "$BUILD_DIR/unsigned.apk"
(cd "$BUILD_DIR/dex" && zip -q -u ../unsigned.apk classes.dex)
"$TOOLS_DIR/zipalign" -f -p 4 "$BUILD_DIR/unsigned.apk" "$BUILD_DIR/aligned.apk"
KEYSTORE_PATH="$TOOLCHAIN_DIR/ieat-development.p12"
if [[ ! -f "$KEYSTORE_PATH" ]]; then
 keytool -genkeypair -keystore "$KEYSTORE_PATH" -storepass android -keypass android -alias ieat-development -keyalg RSA -keysize 2048 -validity 3650 -dname 'CN=iEat Development,O=iEat,C=TJ' -noprompt
fi
java -jar "$TOOLS_DIR/lib/apksigner.jar" sign --ks "$KEYSTORE_PATH" --ks-key-alias ieat-development --ks-pass pass:android --key-pass pass:android --out "$OUTPUT_DIR/iEat-1.0.0-debug.apk" "$BUILD_DIR/aligned.apk"
java -jar "$TOOLS_DIR/lib/apksigner.jar" verify --verbose "$OUTPUT_DIR/iEat-1.0.0-debug.apk"
"$TOOLS_DIR/zipalign" -c -v 4 "$OUTPUT_DIR/iEat-1.0.0-debug.apk" | tail -1
sha256sum "$OUTPUT_DIR/iEat-1.0.0-debug.apk" > "$OUTPUT_DIR/iEat-1.0.0-debug.apk.sha256"
