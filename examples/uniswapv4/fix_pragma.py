import os
import re

SRC_ROOT = "src"  # Carpeta raíz
PRAGMA_REGEX = re.compile(r'pragma solidity\s*([^\s;]+);')

def fix_pragma_in_file(file_path):
    """Reemplaza '=' por '^' en pragma solidity si es necesario"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    match = PRAGMA_REGEX.search(content)
    if match:
        version = match.group(1)
        if version.startswith("="):
            new_version = "^" + version[1:]
            content = PRAGMA_REGEX.sub(f"pragma solidity {new_version};", content)
            with open(file_path, "w", encoding="utf-8") as f_out:
                f_out.write(content)
            print(f"✅ Modificado: {file_path} | {version} -> {new_version}")
        else:
            print(f"ℹ️ Ya tiene ^ o >= : {file_path} -> {version}")
    else:
        print(f"⚠️ No se encontró pragma en: {file_path}")

def main():
    for root, _, files in os.walk(SRC_ROOT):
        for file in files:
            if file.endswith(".sol"):
                fix_pragma_in_file(os.path.join(root, file))
    print("\n🎉 Todos los contratos dentro de src/ y sus subdirectorios tienen pragma corregido a ^.")

if __name__ == "__main__":
    main()
