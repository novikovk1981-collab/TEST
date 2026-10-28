"""Статическая проверка проекта без Android SDK.

Что проверяет:
  * все XML парсятся (манифест, ресурсы, layout, vector);
  * каждая ссылка @string/@color/@style/@drawable/@mipmap/@layout существует;
  * R.id / R.string / R.layout из MainActivity есть в ресурсах;
  * namespace/package/applicationId согласованы;
  * балансы скобок в Java;
  * YAML workflow парсится (если есть pyyaml).
"""

import os
import re
import sys
import glob
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
RES = os.path.join(APP, "src", "main", "res")
JAVA_DIR = os.path.join(APP, "src", "main", "java")

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"

errors = []
warnings = []


def add_err(msg):
    errors.append(msg)


def add_warn(msg):
    warnings.append(msg)


def parse_all_xml():
    files = glob.glob(os.path.join(APP, "src", "main", "**", "*.xml"), recursive=True)
    for path in files:
        try:
            ET.parse(path)
        except ET.ParseError as e:
            add_err(f"XML не парсится: {os.path.relpath(path, ROOT)}: {e}")
    return files


def collect_resources(files):
    res = {"string": set(), "color": set(), "style": set(), "drawable": set(),
           "mipmap": set(), "layout": set(), "id": set(), "xml": set()}

    for path in files:
        rel = os.path.relpath(path, RES).replace("\\", "/")
        parts = rel.split("/")
        folder = parts[0]

        m = re.match(r"^(drawable|mipmap|layout|xml)(-.+)?$", folder)
        if m:
            kind = m.group(1)
            name = os.path.splitext(parts[-1])[0]
            res[kind].add(name)
            continue

        if folder.startswith("values"):
            tree = ET.parse(path)
            for el in tree.getroot():
                tag = el.tag
                name = el.get("name")
                if not name:
                    continue
                if tag == "string":
                    res["string"].add(name)
                elif tag == "color":
                    res["color"].add(name)
                elif tag == "style":
                    res["style"].add(name)
                elif tag == "item" and el.get("type"):
                    kind = el.get("type")
                    if kind in res:
                        res[kind].add(name)
                if el.get("id"):
                    res["id"].add(el.get("id").replace("@+id/", ""))

    # id из layout
    for path in files:
        if "layout" not in os.path.relpath(path, RES).replace("\\", "/"):
            continue
        tree = ET.parse(path)
        for el in tree.iter():
            value = el.get(ANDROID_NS + "id")
            if value:
                res["id"].add(value.replace("@+id/", ""))

    return res


def check_references(files, res):
    pattern = re.compile(r"@(string|color|style|drawable|mipmap|layout|xml)/([A-Za-z0-9_.]+)")
    for path in files:
        text = open(path, encoding="utf-8").read()
        for kind, name in pattern.findall(text):
            if name.startswith("android:"):
                continue
            if name not in res[kind]:
                add_err(f"Ссылка @{kind}/{name} не найдена "
                        f"({os.path.relpath(path, ROOT)})")


def check_java(res):
    java_files = glob.glob(os.path.join(JAVA_DIR, "**", "*.java"), recursive=True)
    if not java_files:
        add_err("Не найдены java-файлы")
        return None

    for path in java_files:
        src = open(path, encoding="utf-8").read()

        stack = []
        pairs = {")": "(", "}": "{", "]": "["}
        for ch in re.sub(r'"(\\.|[^"\\])*"', '""', src):
            if ch in "({[":
                stack.append(ch)
            elif ch in ")}]":
                if not stack or stack.pop() != pairs[ch]:
                    add_err(f"Несбалансированные скобки в {os.path.basename(path)}")
                    stack = None
                    break
        if stack:
            add_err(f"Незакрытые скобки в {os.path.basename(path)}")

        for kind, name in re.findall(r"\bR\.(id|string|layout|mipmap|drawable|color)\.([A-Za-z0-9_]+)", src):
            if name not in res.get(kind, set()):
                add_err(f"R.{kind}.{name} отсутствует в ресурсах")

        m = re.search(r"^\s*package\s+([\w.]+);", src, re.M)
        if not m:
            add_err(f"В {os.path.basename(path)} нет package")
        else:
            pkg = m.group(1)
            gradle = open(os.path.join(APP, "build.gradle"), encoding="utf-8").read()
            ns = re.search(r"namespace\s+'([\w.]+)'", gradle)
            manifest_pkg = os.path.join(APP, "src", "main", "AndroidManifest.xml")
            mtext = open(manifest_pkg, encoding="utf-8").read()
            m_activity = re.search(r'android:name="\.([\w.]+)"', mtext)
            if ns and ns.group(1) != pkg:
                add_err(f"namespace '{ns.group(1)}' != package '{pkg}'")
            if m_activity:
                cls = os.path.join(JAVA_DIR, *pkg.split("."), m_activity.group(1) + ".java")
                if not os.path.exists(cls):
                    add_err(f"Activity {pkg}.{m_activity.group(1)} не найдена")

    gradle = open(os.path.join(APP, "build.gradle"), encoding="utf-8").read()
    for key in ("applicationId", "buildConfigField", "compileSdk", "minSdk", "targetSdk"):
        if key not in gradle:
            add_err(f"В app/build.gradle нет {key}")
    if "START_URL" not in gradle:
        add_err("В app/build.gradle нет START_URL")
    if "BuildConfig.START_URL" not in open(java_files[0], encoding="utf-8").read():
        add_err("MainActivity не использует BuildConfig.START_URL")

    return java_files[0]


def check_yaml():
    path = os.path.join(ROOT, ".github", "workflows", "build-apk.yml")
    if not os.path.exists(path):
        add_err("Нет workflow .github/workflows/build-apk.yml")
        return
    try:
        import yaml  # noqa
    except ImportError:
        add_warn("pyyaml не установлен — YAML не проверен")
        return
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data.get("jobs"), dict):
        add_err("workflow: нет jobs")


def check_icons():
    for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        for name in ("ic_launcher.png", "ic_launcher_round.png"):
            p = os.path.join(RES, f"mipmap-{d}", name)
            if not os.path.exists(p):
                add_err(f"Нет иконки res/mipmap-{d}/{name}")


def main():
    files = parse_all_xml()
    res = collect_resources(files)
    check_references(files, res)
    java = check_java(res)
    check_yaml()
    check_icons()

    print(f"XML-файлов: {len(files)}")
    print("Ресурсы:", {k: len(v) for k, v in res.items()})
    if java:
        print("Java:", os.path.relpath(java, ROOT))

    if warnings:
        print("\nПРЕДУПРЕЖДЕНИЯ:")
        for w in warnings:
            print("  ⚠", w)

    if errors:
        print("\nОШИБКИ:")
        for e in errors:
            print("  ✗", e)
        return 1

    print("\n✓ Проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
