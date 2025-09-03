import os
import re
import json

ROOT_DIR = os.getcwd()
SRC_DIR = "src"  # Solo src/
TEST_DIRS = ["src/test"]  # Ignorar tests

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

def is_test_file(file_path):
    for test_dir in TEST_DIRS:
        if file_path.startswith(test_dir):
            return True
    return False

def collect_sources():
    """Recolecta todos los contratos de src/, ignorando tests"""
    sources = {}
    for root, _, files in os.walk(SRC_DIR):
        for f in files:
            if f.endswith(".sol"):
                path = os.path.join(root, f)
                norm_path = path.replace("\\", "/")
                if is_test_file(norm_path):
                    continue
                sources[norm_path] = {"urls": [norm_path]}
    return sources

def generate_input_json():
    data = {
        "language": "Solidity",
        "sources": collect_sources(),
        "settings": {
            "optimizer": {"enabled": True, "runs": 800},
            "evmVersion": "cancun",
            "outputSelection": {
                "*": {
                    "*": ["abi", "evm.bytecode", "evm.deployedBytecode"]
                }
            }
        }
    }
    with open("input.json", "w") as f:
        json.dump(data, f, indent=2)
    print("✅ input.json generado con los contratos de src/ (sin tests).")

def main():
    for root, _, files in os.walk(SRC_DIR):
        for file in files:
            if file.endswith(".sol"):
                path = os.path.join(root, file)
                norm_path = path.replace("\\", "/")
                if is_test_file(norm_path):
                    continue
                fix_pragma_in_file(path)
    generate_input_json()
    print("\n🎉 Todo listo. Compila con:")
    print("solc --standard-json < input.json > output.json")

if __name__ == "__main__":
    main()
