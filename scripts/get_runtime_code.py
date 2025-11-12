"""
Descarga el bytecode (runtime) de un conjunto de contratos en Ethereum
usando la API de Etherscan V2.

Requisitos:
    pip install requests

Uso:
    python get_bytecode_from_etherscan_v2.py addresses.txt <API_KEY>
"""

import sys
import requests
import time
import os


def get_bytecode(address, api_key):
    url = (
        f"https://api.etherscan.io/v2/api"
        f"?chainid=1"
        f"&module=proxy"
        f"&action=eth_getCode"
        f"&address={address}"
        f"&tag=latest"
        f"&apikey={api_key}"
    )
    r = requests.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()
    print(data)  # ver la respuesta completa
    code = data.get("result")
    if code is None or code == "0x":
        return None
    return code

def main():
    test_path = "/Users/pablo/Repositorios/ethereum/grey/scripts/test_stack_too_deep/"
    addresses_file = os.listdir(test_path)

    addresses = [x.strip().split("/")[-1] for x in addresses_file]
    api_key = 'WWGB4TWWWWPF9AH71J7UXYK3T2ACCADZRZ'

    print(f"Obteniendo bytecodes de {len(addresses)} direcciones...\n")

    results = {}
    for addr in addresses:
        try:
            code = get_bytecode(addr, api_key)
            if code:
                print(code)
                print(f"✅ {addr}: {len(code)//2} bytes")
                results[addr] = code
            else:
                print(f"⚠️ {addr}: sin código (EOA o selfdestruct)")
        except Exception as e:
            print(f"❌ Error con {addr}: {e}")
        time.sleep(0.2)  # respetar rate limit de Etherscan (5 req/s)

        # Guardar resultados
        output_path = os.path.join(test_path, addr, f"{addr}.output")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            if code:
                f.write(code.lstrip("0x"))

    print("\n✅ Bytecodes guardados.")

if __name__ == "__main__":
    main()
