#!/usr/bin/env python3
"""
Estadísticas de la reparación de grey (stack-too-deep) a partir de los repair_*.csv que deja cada contrato en un
directorio de ejecución (test_opt8, test_most_called_opt8, test_stack_too_deep, ...). Es lo que contaba
count_repair_stats.txt, y lo que usa el párrafo de las reparaciones de la sección de experimentos del paper:

  - programas analizados y programas con alguna reparación (num_assigned > 0);
  - variables guardadas en memoria (num_assigned: es la cifra que el paper llama "VGET annotations") y anotaciones
    VGET reales (num_vget), VSET y DUP-VSET;
  - registros: colores (num_colors) y huecos de memoria reservados (memory_slots);
  - phi-functions que no se pueden clonar (num_phi) y en cuántos programas aparecen;
  - el programa con más variables por registro (el ejemplo del paper: "30 variables, 6 phi, 12 registros").

Uso: python3 repair_stats.py <directorio> [<directorio> ...] [--only-tests] [--repair-from DIR]
  --only-tests: solo los directorios que tienen fichero test (los semantic tests que se ejecutan)
  --repair-from DIR: lee los repair_*.csv de DIR/<programa> en vez de <directorio>/<programa>. run_experiments_macos.sh
                     no los copia al directorio del test: se quedan en la carpeta de salida de grey, /tmp/<test>, que
                     solo guarda los de la última configuración ejecutada (p. ej. --repair-from /private/tmp)
Ejemplo: python3 repair_stats.py test_opt8 test_most_called_opt8 test_stack_too_deep
"""
import argparse
import csv
import glob
import os

COLUMNS = ["num_phi", "num_assigned", "num_colors", "memory_slots", "num_vget", "num_vset", "num_dup_vset",
           "redundant_stores", "before_constants"]


def read_program(directory: str):
    """Suma de las columnas de los repair_*.csv de un programa (una fila por cada objeto o contrato reparado)"""
    totals = {column: 0 for column in COLUMNS}
    files = glob.glob(os.path.join(directory, "repair_*.csv"))
    if not files:
        return None
    for path in files:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                for column in COLUMNS:
                    try:
                        totals[column] += int(float(row.get(column) or 0))
                    except ValueError:
                        pass
    return totals


def summarize(base: str, only_tests: bool, repair_from: str = None) -> None:
    programs = {}
    for directory in sorted(glob.glob(os.path.join(base, "*/"))):
        if only_tests and not os.path.exists(os.path.join(directory, "test")):
            continue
        name = os.path.basename(directory.rstrip("/"))
        totals = read_program(os.path.join(repair_from, name) if repair_from else directory)
        if totals is not None:
            programs[os.path.basename(directory.rstrip("/"))] = totals

    repaired = {name: t for name, t in programs.items() if t["num_assigned"] > 0}
    total = {column: sum(t[column] for t in programs.values()) for column in COLUMNS}

    print(f"===== {base}{' (solo tests con test)' if only_tests else ''}"
          f"{f' (repair_*.csv de {repair_from})' if repair_from else ''}")
    print(f"programas con repair_*.csv:                 {len(programs)}")
    print(f"programas con alguna reparación:            {len(repaired)}")
    print(f"variables guardadas en memoria (num_assigned, 'VGET annotations' en el paper): {total['num_assigned']:,}")
    print(f"anotaciones VGET (num_vget):                {total['num_vget']:,}")
    print(f"anotaciones VSET / DUP-VSET:                {total['num_vset']:,} / {total['num_dup_vset']:,}")
    print(f"registros (num_colors):                     {total['num_colors']:,}")
    print(f"huecos de memoria reservados (memory_slots): {total['memory_slots']:,}")
    print(f"phi-functions no clonables (num_phi):       {total['num_phi']:,} "
          f"(en {sum(1 for t in programs.values() if t['num_phi'] > 0)} programas)")
    print(f"variables resueltas con constantes antes de reparar (before_constants): {total['before_constants']:,}")
    print(f"almacenamientos redundantes eliminados (redundant_stores): {total['redundant_stores']:,}")
    if repaired:
        # El ejemplo del paper: el programa en el que más variables comparten registro
        name, t = max(repaired.items(), key=lambda item: (item[1]["num_assigned"] - item[1]["num_colors"],
                                                          item[1]["num_assigned"]))
        print(f"más variables por registro: {name}: {t['num_assigned']} variables en {t['num_colors']} registros "
              f"({t['num_phi']} phi no clonables, {t['num_vget']} VGET)")
        name, t = max(repaired.items(), key=lambda item: item[1]["num_assigned"])
        print(f"más variables reparadas:    {name}: {t['num_assigned']} variables en {t['num_colors']} registros "
              f"({t['num_phi']} phi no clonables, {t['num_vget']} VGET)")


def main():
    parser = argparse.ArgumentParser(description="Estadísticas de la reparación de grey a partir de los repair_*.csv")
    parser.add_argument("directories", nargs="+", help="directorios de ejecución (test_opt8, test_most_called_opt8...)")
    parser.add_argument("--only-tests", action="store_true", help="solo los directorios con fichero test")
    parser.add_argument("--repair-from", dest="repair_from", default=None,
                        help="carpeta de la que leer los repair_*.csv de cada programa (p. ej. /private/tmp)")
    args = parser.parse_args()
    for base in args.directories:
        summarize(base, args.only_tests, args.repair_from)


if __name__ == "__main__":
    main()
