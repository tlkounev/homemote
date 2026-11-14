#!/usr/bin/env python3
"""Sestavení APK Homemote (pomocník na TV + aplikace pro telefon) bez Gradlu a Android SDK.

Kroky: javac (proti android.jar) -> dx (classes.dex) -> vlastní kodér binárního
AndroidManifest.xml (AXML) -> ZIP -> podpis v1+v2+v3 (uber-apk-signer).
APK nemá resources.arsc (žádné zdroje), Android takové APK normálně nainstaluje.

Nástroje se stáhnou do ./tools při prvním běhu:
  android.jar (API 34)      github.com/Sable/android-platforms
  dx-30.0.2.jar             součást dex-tools (github.com/pxb1988/dex2jar)
  uber-apk-signer-1.3.0.jar github.com/patrickfav/uber-apk-signer
Potřeba: JDK 17+ (javac, keytool), Python 3.

Použití:  python3 android/build.py [helper] [phone]
Každá aplikace má složku s app.json, AndroidManifest.xml, src/ a volitelně assets/.
Proměnné prostředí (backend je nastavuje sám, viz app/android_build.py):
  HM_OUT    kam zkopírovat hotová APK (složka data backendu)
  HM_WORK   pracovní složka sestavení (výchozí <aplikace>/build)
  HM_KEYS   složka s podpisovými klíči (výchozí <aplikace>/keystore)
  HM_TOOLS  složka nástrojů (výchozí android/tools)
Zdrojová složka může být jen pro čtení – zapisuje se jen do HM_WORK, HM_KEYS, HM_TOOLS a HM_OUT.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import json

REPO = Path(__file__).resolve().parent
TOOLS = Path(os.environ.get("HM_TOOLS", REPO / "tools"))
KS_PASS = "homemote"  # klíč jen pro podpis sideload APK, ne tajemství
KS_ALIAS = "homemote"
APPS = ["helper", "phone"]

TOOL_URLS = {
    "android.jar": "https://raw.githubusercontent.com/Sable/android-platforms/master/android-34/android.jar",
    "dex-tools.zip": "https://github.com/pxb1988/dex2jar/releases/download/v2.4/dex-tools-v2.4.zip",
    "uber-apk-signer.jar": "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar",
}

ANDROID_NS = "http://schemas.android.com/apk/res/android"
# android.R.attr (z android.jar, javap -constants)
ATTR_IDS = {
    "theme": 0x01010000, "label": 0x01010001, "icon": 0x01010002, "name": 0x01010003,
    "permission": 0x01010006, "exported": 0x01010010, "enabled": 0x0101000E,
    "minSdkVersion": 0x0101020C, "versionCode": 0x0101021B, "versionName": 0x0101021C,
    "targetSdkVersion": 0x01010270, "allowBackup": 0x01010280, "required": 0x0101028E,
    "banner": 0x010103F2, "usesCleartextTraffic": 0x010104EC,
    "launchMode": 0x0101001D, "configChanges": 0x0101001F, "scheme": 0x01010027, "host": 0x01010028,
    "windowSoftInputMode": 0x0101022B,
}
INT_ATTRS = {"versionCode", "minSdkVersion", "targetSdkVersion", "launchMode", "configChanges", "windowSoftInputMode"}
BOOL_ATTRS = {"exported", "required", "allowBackup", "enabled", "usesCleartextTraffic"}

T_REFERENCE, T_STRING, T_INT_DEC, T_INT_BOOLEAN = 0x01, 0x03, 0x10, 0x12


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


# --- nástroje -----------------------------------------------------------------------
def ensure_tools() -> dict[str, Path]:
    TOOLS.mkdir(parents=True, exist_ok=True)
    for name, url in TOOL_URLS.items():
        dst = TOOLS / name
        if not dst.exists():
            log(f"stahuji {name}")
            with urllib.request.urlopen(url, timeout=300) as r:
                dst.write_bytes(r.read())
    dx = TOOLS / "dx.jar"
    if not dx.exists():
        with zipfile.ZipFile(TOOLS / "dex-tools.zip") as z:
            member = next(n for n in z.namelist() if re.search(r"/lib/dx-[\d.]+\.jar$", n))
            dx.write_bytes(z.read(member))
    return {"android": TOOLS / "android.jar", "dx": dx, "signer": TOOLS / "uber-apk-signer.jar"}


def run(*cmd: str) -> None:
    log(" ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


# --- binární AndroidManifest.xml (AXML) -----------------------------------------------
class Axml:
    def __init__(self) -> None:
        self.strings: list[str] = []
        self.index: dict[str, int] = {}
        self.res_ids: list[int] = []

    def s(self, value: str) -> int:
        if value not in self.index:
            self.index[value] = len(self.strings)
            self.strings.append(value)
        return self.index[value]

    def encode(self, xml_text: str) -> bytes:
        root = ET.fromstring(xml_text)
        # 1) Názvy atributů s ID musí být na začátku string poolu ve stejném pořadí jako resource map.
        attr_names = []
        for el in root.iter():
            for key in el.attrib:
                ns, local = split(key)
                if ns == ANDROID_NS and local in ATTR_IDS and local not in attr_names:
                    attr_names.append(local)
        attr_names.sort(key=lambda n: ATTR_IDS[n])
        for n in attr_names:
            self.s(n)
            self.res_ids.append(ATTR_IDS[n])
        self.s("android")
        self.s(ANDROID_NS)

        body = io.BytesIO()
        ns_chunk = struct.pack("<IIii", 1, 0xFFFFFFFF, self.s("android"), self.s(ANDROID_NS))
        body.write(chunk(0x0100, 16, ns_chunk))
        self._element(root, body)
        body.write(chunk(0x0101, 16, ns_chunk))

        pool = self._pool()
        resmap = chunk(0x0180, 8, b"".join(struct.pack("<I", i) for i in self.res_ids))
        content = pool + resmap + body.getvalue()
        return struct.pack("<HHI", 0x0003, 8, 8 + len(content)) + content

    def _element(self, el: ET.Element, out: io.BytesIO) -> None:
        ns, tag = split(el.tag)
        attrs = []
        for key, raw in el.attrib.items():
            ans, local = split(key)
            if ans == ANDROID_NS:
                if local not in ATTR_IDS:
                    raise SystemExit(f"neznámý atribut android:{local} – doplňte ATTR_IDS")
                attrs.append((ATTR_IDS[local], self.s(ANDROID_NS), local, raw))
            else:
                attrs.append((0, -1, local, raw))
        attrs.sort(key=lambda a: a[0])  # bez ID první, pak vzestupně podle ID (AttributeResolution to vyžaduje)
        data = io.BytesIO()
        data.write(struct.pack("<iiHHHHHH", -1, self.s(tag), 20, 20, len(attrs), 0, 0, 0))
        for _rid, ans_idx, local, raw in attrs:
            name_idx = self.s(local)
            vtype, vdata, raw_idx = self._value(local, raw, ans_idx != -1)
            data.write(struct.pack("<iiiHBBI", ans_idx, name_idx, raw_idx, 8, 0, vtype, vdata))
        out.write(chunk(0x0102, 16, struct.pack("<Ii", 1, -1) + data.getvalue(), raw_header=True))
        for child in el:
            self._element(child, out)
        out.write(chunk(0x0103, 16, struct.pack("<Ii", 1, -1) + struct.pack("<ii", -1, self.s(tag)), raw_header=True))

    def _value(self, local: str, raw: str, android: bool) -> tuple[int, int, int]:
        if android and local in INT_ATTRS:
            return T_INT_DEC, int(raw, 0) & 0xFFFFFFFF, -1
        if android and local in BOOL_ATTRS:
            return T_INT_BOOLEAN, 0xFFFFFFFF if raw.lower() == "true" else 0, -1
        if raw.startswith("@0x"):
            return T_REFERENCE, int(raw[1:], 16), -1
        idx = self.s(raw)
        return T_STRING, idx, idx

    def _pool(self) -> bytes:
        offsets, data = [], io.BytesIO()
        for st in self.strings:
            offsets.append(data.tell())
            enc = st.encode("utf-16-le")
            n = len(enc) // 2
            if n > 0x7FFF:
                raise SystemExit("řetězec je příliš dlouhý")
            data.write(struct.pack("<H", n) + enc + b"\x00\x00")
        raw = data.getvalue()
        raw += b"\x00" * ((4 - len(raw) % 4) % 4)
        header_size = 28
        strings_start = header_size + 4 * len(self.strings)
        head = struct.pack("<IIIII", len(self.strings), 0, 0, strings_start, 0)
        body = head + b"".join(struct.pack("<I", o) for o in offsets) + raw
        return struct.pack("<HHI", 0x0001, header_size, 8 + len(body)) + body


def string_pool(strings: list[str]) -> bytes:
    a = Axml()
    for st in strings:
        a.s(st)
    return a._pool()


def icon_arsc(package: str, icon_path: str) -> bytes:
    """resources.arsc s jediným zdrojem: drawable/icon (PNG, hustota xxxhdpi) = 0x7f010000."""
    gpool = string_pool([icon_path])
    tpool = string_pool(["drawable"])
    kpool = string_pool(["icon"])
    # typeSpec: 1 položka, liší se hustotou (CONFIG_DENSITY = 0x0100)
    type_spec = struct.pack("<HHIBBHI", 0x0202, 16, 16 + 4, 1, 0, 0, 1) + struct.pack("<I", 0x0100)
    config = bytearray(64)
    struct.pack_into("<I", config, 0, 64)
    struct.pack_into("<H", config, 14, 640)   # density xxxhdpi
    struct.pack_into("<H", config, 24, 4)     # sdkVersion v4 (jako aapt u hustot)
    header_size = 8 + 1 + 1 + 2 + 4 + 4 + 64
    entries_start = header_size + 4
    entry = struct.pack("<HHI", 8, 0, 0) + struct.pack("<HBBI", 8, 0, T_STRING, 0)
    type_chunk = struct.pack("<HHIBBHII", 0x0201, header_size, entries_start + len(entry), 1, 0, 0, 1, entries_start) \
        + bytes(config) + struct.pack("<I", 0) + entry
    name = package.encode("utf-16-le")[:254].ljust(256, b"\x00")
    pkg_header = 288
    body = tpool + kpool + type_spec + type_chunk
    pkg = struct.pack("<HHII", 0x0200, pkg_header, pkg_header + len(body), 0x7F) + name \
        + struct.pack("<IIIII", pkg_header, 1, pkg_header + len(tpool), 1, 0) + body
    content = gpool + pkg
    return struct.pack("<HHII", 0x0002, 12, 12 + len(content), 1) + content


def split(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        ns, local = name[1:].split("}", 1)
        return ns, local
    return None, name


def chunk(ctype: int, header_size: int, payload: bytes, raw_header: bool = False) -> bytes:
    """payload = zbytek hlavičky (za type/headerSize/size) + data."""
    return struct.pack("<HHI", ctype, header_size, 8 + len(payload)) + payload


# --- build --------------------------------------------------------------------------------
def build_app(name: str, tools: dict[str, Path]) -> Path:
    app_dir = REPO / name
    cfg = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    pkg, vname, vcode = cfg["package"], cfg["version_name"], int(cfg["version_code"])
    log(f"=== {name}: {pkg} {vname} ({vcode})")
    build = Path(os.environ["HM_WORK"]) / name if os.environ.get("HM_WORK") else app_dir / "build"
    if build.exists():
        shutil.rmtree(build)
    classes = build / "classes"
    classes.mkdir(parents=True)

    gen = build / "gen" / Path(*pkg.split("."))
    gen.mkdir(parents=True)
    (gen / "BuildInfo.java").write_text(
        f"package {pkg};\n"
        f"public final class BuildInfo {{ public static final String VERSION_NAME = \"{vname}\"; "
        f"public static final int VERSION_CODE = {vcode}; private BuildInfo() {{ }} }}\n",
        encoding="utf-8",
    )
    sources = [str(p) for p in sorted((app_dir / "src").rglob("*.java"))] + [str(gen / "BuildInfo.java")]
    run("javac", "-nowarn", "-Xlint:-options", "-encoding", "UTF-8", "-source", "8", "-target", "8",
        "-bootclasspath", tools["android"], "-classpath", tools["android"], "-d", classes, *sources)
    dex = build / "classes.dex"
    run("java", "-cp", tools["dx"], "com.android.dx.command.Main", "--dex", f"--min-sdk-version={cfg['min_sdk']}",
        f"--output={dex}", classes)

    manifest_src = (app_dir / "AndroidManifest.xml").read_text(encoding="utf-8")
    manifest_src = manifest_src.replace("@VERSION_CODE@", str(vcode)).replace("@VERSION_NAME@", vname)
    manifest_src = manifest_src.replace("@ICON@", "@0x7f010000")
    axml = Axml().encode(manifest_src)
    (build / "AndroidManifest.xml").write_bytes(axml)

    unsigned = build / f"{name}-unsigned.apk"
    stamp = (2008, 1, 1, 0, 0, 0)
    icon = app_dir / cfg["icon"] if cfg.get("icon") else None
    with zipfile.ZipFile(unsigned, "w") as z:
        if icon:
            # resources.arsc musí být nekomprimovaný a zarovnaný na 4 B (targetSdk >= 30): jako první položka
            # leží data na offsetu 30 + len("resources.arsc") = 44.
            icon_path = "res/drawable-xxxhdpi-v4/icon.png"
            arsc = icon_arsc(pkg, icon_path)
            zi = zipfile.ZipInfo("resources.arsc", stamp)
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, arsc)
            z.writestr(zipfile.ZipInfo(icon_path, stamp), icon.read_bytes(), zipfile.ZIP_STORED)
        z.writestr(zipfile.ZipInfo("AndroidManifest.xml", stamp), axml, zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("classes.dex", stamp), dex.read_bytes(), zipfile.ZIP_DEFLATED)
        assets = app_dir / "assets"
        if assets.is_dir():
            for f in sorted(p for p in assets.rglob("*") if p.is_file()):
                z.writestr(zipfile.ZipInfo("assets/" + f.relative_to(assets).as_posix(), stamp), f.read_bytes(),
                           zipfile.ZIP_DEFLATED)

    keystore = (Path(os.environ["HM_KEYS"]) if os.environ.get("HM_KEYS") else app_dir / "keystore") / f"homemote-{name}.jks"
    if not keystore.exists():
        keystore.parent.mkdir(parents=True, exist_ok=True)
        run("keytool", "-genkeypair", "-keystore", keystore, "-storepass", KS_PASS, "-keypass", KS_PASS,
            "-alias", KS_ALIAS, "-keyalg", "RSA", "-keysize", "2048", "-validity", "36500",
            "-dname", f"CN=Homemote {name}, O=Homemote")
    out = build / "signed"
    run("java", "-jar", tools["signer"], "--apks", unsigned, "--out", out, "--ks", keystore,
        "--ksAlias", KS_ALIAS, "--ksPass", KS_PASS, "--ksKeyPass", KS_PASS, "--allowResign",
        "--skipZipAlign")  # APK nemá resources.arsc, zarovnání není potřeba (a nativní zipalign se nespouští)
    final = build / cfg["apk"]
    shutil.copy(next(out.glob("*.apk")), final)
    log(f"hotovo: {final} ({final.stat().st_size} B)")
    out_dir = os.environ.get("HM_OUT")
    if out_dir:
        shutil.copy(final, Path(out_dir) / cfg["apk"])
        log(f"zkopírováno do {Path(out_dir) / cfg['apk']}")
    return final


def main() -> None:
    tools = ensure_tools()
    names = sys.argv[1:] or APPS
    for name in names:
        build_app(name, tools)
    log("HOTOVO: " + ", ".join(names))


if __name__ == "__main__":
    sys.exit(main())
