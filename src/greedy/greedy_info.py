"""
Module for computing relevant information from the greedy algorithm
"""
from typing import List, Set, Dict
from collections import Counter, defaultdict
from global_params.types import var_id_T, instr_id_T, instr_JSON_T


def compute_instr_id2var(json_instrs: List[instr_JSON_T]) -> Dict[var_id_T, List[instr_id_T]]:
    instr_id2var = dict()
    for instr in json_instrs:
        if len(instr["outpt_sk"]) > 0:
            instr_id2var[instr["id"]] = instr["outpt_sk"]
    return instr_id2var


class GreedyInfo:

    def __init__(self, greedy_ids: List[str], outcome: str, execution_time: float,
                 get_count: Counter, elements_to_fix: Set[var_id_T], reachable: Dict[var_id_T, int],
                 instr_id2var: Dict[var_id_T, List[instr_id_T]]):
        self.greedy_ids = greedy_ids if greedy_ids else []
        self.outcome = outcome
        self.execution_time = execution_time
        self.get_count = get_count
        self.elements_to_fix = elements_to_fix
        self.reachable = reachable
        self.unreachable = {}
        self.instr_id2var = instr_id2var
        # Elements that are accessed through get instructions.
        # Considers GET-SET elements.
        self.get_elements = Counter(id_instr[4:-1] for id_instr in self.greedy_ids
                                    if "GET" in id_instr)

    @classmethod
    def from_new_version(cls, greedy_ids: List[str], outcome: str, execution_time: float, original_instrs: List[instr_JSON_T],
                 get_count: Counter, elements_to_fix: Set[var_id_T], reachable: Dict[var_id_T, int]) -> 'GreedyInfo':
        instr_id2var = compute_instr_id2var(original_instrs)
        return GreedyInfo(greedy_ids, outcome, execution_time, get_count, elements_to_fix, reachable, instr_id2var)

    @classmethod
    def from_old_version(cls, greedy_ids: List[str], outcome: str,
                         execution_time: float, original_instrs: List[instr_JSON_T]):
        instr_id2var = compute_instr_id2var(original_instrs)
        return GreedyInfo(greedy_ids, outcome, execution_time, Counter(), set(), dict(), instr_id2var)
