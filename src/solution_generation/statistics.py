from typing import Dict, List


def generate_statistics_info(block_id: str, solution_found: List[str], greedy_time: float,
                             original_sfs: Dict) -> Dict:
    csv_row = {"block_id": block_id, "original_instrs": original_sfs["yul_expressions"]}
    csv_row.update(**{"solution_found": '\n'.join(solution_found) if solution_found is not None else "",
                      "time": greedy_time, "source_stack": original_sfs["src_ws"],
                      "target_stack": original_sfs["tgt_ws"]})
    return csv_row
