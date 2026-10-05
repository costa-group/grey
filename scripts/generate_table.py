#!/usr/bin/env python3
"""
Genera la tabla de experimentos (table-experiments.tex) ejecutando get_stats.sh / get_stats_most_called.sh sobre los
ficheros de salida de cada configuración:
  h1          -> <prefijo>-<conjunto>-<modo>-junk
  h1.2        -> <prefijo>-<conjunto>-<modo>
  h1.2^{cd=N} -> <prefijo>-<conjunto>-<modo>N   (o <prefijo>-<conjunto>-<modo>-N)
con <conjunto> = test (filas Test) o mostcalled (filas MC) y <modo> = opt o noopt.

Uso: python3 generate_table.py <prefijo> opt|noopt|both [-d 8] [-o tabla.tex]
     both: una sola tabla con noopt arriba y opt abajo, separados por una doble línea; las métricas de opt llevan el
           superíndice opt (\#Ins$^{opt}_{Test}$, ...)
     p.ej. python3 generate_table.py salida noopt   (usa salida-test-noopt, salida-mostcalled-noopt-junk, ...)
Se ejecuta desde el directorio scripts (get_stats*.sh usan rutas relativas). Los get_stats se ejecutan uno detrás de
otro, porque escriben sus ficheros intermedios (num_instructions.txt, ...) en el directorio actual.
"""
import argparse
import os
import re
import subprocess
import sys

STATS_SCRIPT = {"test": "get_stats.sh", "mostcalled": "get_stats_most_called.sh"}


def output_file(prefix: str, dataset: str, mode: str, variant: str, depth: int) -> str:
    """Fichero de salida de la configuración (variant: junk, normal o depth)"""
    base = f"{prefix}-{dataset}-{mode}"
    candidates = {"junk": [f"{base}-junk"], "normal": [base], "depth": [f"{base}{depth}", f"{base}-{depth}"]}[variant]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    sys.exit(f"No se encuentra el fichero de salida para {dataset} {mode} {variant}: {' ni '.join(candidates)}")


def run_stats(dataset: str, res_file: str) -> dict:
    """Ejecuta el get_stats correspondiente y devuelve los totales de instrucciones y bytes de solc y de grey"""
    env = dict(os.environ, MPLBACKEND="Agg")   # sin ventanas de matplotlib
    print(f"  bash {STATS_SCRIPT[dataset]} {res_file}", file=sys.stderr)
    out = subprocess.run(["bash", STATS_SCRIPT[dataset], res_file], capture_output=True, text=True, env=env).stdout

    def number(pattern: str, text: str) -> int:
        match = re.search(pattern, text, re.M)
        if match is None:
            sys.exit(f"No se encuentra '{pattern}' en la salida de {STATS_SCRIPT[dataset]} {res_file}")
        return int(match.group(1))

    bytes_section = out[out.find("===== BYTES STATISTICS ====="):]
    return {"solc_ins": number(r"^SUM ORIGIN NUM INS: (\d+)$", out),
            "grey_ins": number(r"^SUM OPT NUM INS: (\d+)$", out),
            "solc_bytes": number(r"^TOTAL BYTES ORIGINAL: (\d+)$", bytes_section),
            "grey_bytes": number(r"^TOTAL BYTES OPT: (\d+)$", bytes_section)}


def fmt(n: int) -> str:
    return f"{n:,}"


def delta(solc: int, grey: int) -> str:
    return f"{fmt(solc - grey)} ({(solc - grey) / solc * 100:.2f}\\%)"


def rows(dataset_label: str, stats: dict, superscript: str = "") -> str:
    lines = []
    for metric, key in (("Ins", "ins"), ("Bytes", "bytes")):
        solc_values = {stats[v][f"solc_{key}"] for v in stats}
        if len(solc_values) != 1:
            print(f"  AVISO: el total de solc ({metric}, {dataset_label}) no coincide entre configuraciones: "
                  f"{ {v: stats[v][f'solc_{key}'] for v in stats} }", file=sys.stderr)
        solc = stats["normal"][f"solc_{key}"]
        grey = [stats[v][f"grey_{key}"] for v in ("junk", "normal", "depth")]
        label = f"$^{{{superscript}}}_{{{dataset_label}}}$" if superscript else f"$_{{{dataset_label}}}$"
        lines.append(f"  \\#{metric}{label} & {fmt(solc)} & " + " & ".join(fmt(g) for g in grey) + " &\n"
                     f"  " + " & ".join(delta(stats[v][f'solc_{key}'], stats[v][f'grey_{key}'])
                                        for v in ("junk", "normal", "depth")) + " \\\\ ")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Genera la tabla de experimentos a partir de los ficheros salida-*")
    parser.add_argument("prefix", help="prefijo de los ficheros de salida (p.ej. salida -> salida-test-noopt, ...)")
    parser.add_argument("mode", choices=["opt", "noopt", "both"])
    parser.add_argument("-d", "--depth", type=int, default=8, help="profundidad de la versión h1.2^{cd} (por defecto 8)")
    parser.add_argument("-o", "--output", help="fichero .tex de salida (por defecto, la salida estándar)")
    args = parser.parse_args()

    modes = ["noopt", "opt"] if args.mode == "both" else [args.mode]
    stats_by_mode = {}
    for mode in modes:
        stats_by_mode[mode] = {}
        for dataset in ("test", "mostcalled"):
            stats_by_mode[mode][dataset] = {}
            for variant in ("junk", "normal", "depth"):
                stats_by_mode[mode][dataset][variant] = run_stats(
                    dataset, output_file(args.prefix, dataset, mode, variant, args.depth))

    if args.mode == "both":
        # noopt arriba y opt abajo, separados por una doble línea (Test y MC, por una simple, dentro de cada bloque)
        body = "\n  \\hline\n".join([rows("Test", stats_by_mode["noopt"]["test"]),
                                       rows("MC", stats_by_mode["noopt"]["mostcalled"])])
        body += "\n  \\hline\\hline\n"
        body += "\n  \\hline\n".join([rows("Test", stats_by_mode["opt"]["test"], "opt"),
                                        rows("MC", stats_by_mode["opt"]["mostcalled"], "opt")])
    else:
        stats = stats_by_mode[args.mode]
        body = rows("Test", stats["test"]) + "\n  \\hline\\hline\n" + rows("MC", stats["mostcalled"])

    cd = args.depth
    table = f"""\\begin{{table}}[t]\\vspace{{-0.15cm}}
\\vspace{{-0.15cm}}
  \\begin{{adjustbox}}{{width=\\textwidth}}
\\begin{{tabular}}{{|l|r|r|r|r||r|r|r|}}
\\hline
 \\textbf{{Metric}} & \\textbf{{\\textsc{{solc}}}} & \\textbf{{\\toolname$_{{h1}}$}} & \\textbf{{\\toolname$_{{h1.2}}$}} & \\textbf{{\\toolname$^{{cd={cd}}}_{{h1.2}}$}} &\\textbf{{$\\Delta_{{h1}}$(\\%)}} & \\textbf{{$\\Delta_{{h1.2}}$(\\%)}}& \\textbf{{$\\Delta^{{cd={cd}}}_{{h1.2}}$(\\%)}} \\\\ \\hline\\hline
{body}
  \\hline
\\end{{tabular}}
  \\end{{adjustbox}}
  \\secbeg\\secbeg\\vspace{{-0.15cm}}
\\caption{{Experimental results and comparison with \\textsc{{solc}} for
  set \\emph{{Test}} and \\emph{{MC}}.}}
\\label{{table:stats}}\\vspace{{-0.15cm}}
\\vspace{{-0.15cm}}
\\end{{table}}\\vspace{{-0.15cm}}
\\secbeg\\secbeg\\secbeg\\secbeg
"""
    if args.output:
        with open(args.output, "w") as f:
            f.write(table)
        print(f"Tabla escrita en {args.output}", file=sys.stderr)
    else:
        print(table)


if __name__ == "__main__":
    main()
