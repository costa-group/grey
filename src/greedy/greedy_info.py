"""
Module for computing relevant information from the greedy algorithm
"""
from typing import List, Set, Dict, Iterable, Tuple
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
                 original_instrs: List[instr_JSON_T]):
        self.greedy_ids = greedy_ids if greedy_ids else []
        self.outcome = outcome
        self.execution_time = execution_time
        self.reachable: Dict[var_id_T, Tuple[int, int, bool]] = dict()
        self.unreachable: Set[var_id_T] = set()
        self.user_instrs = original_instrs
        self.instr_id2var = compute_instr_id2var(original_instrs)

        # Elements that are accessed through get instructions.
        # Considers VGET-VSET elements.
        self.get_count = Counter(id_instr[5:-1] for id_instr in self.greedy_ids
                                 if "VGET" in id_instr)

        # Elements that might need to be copied in order to propagate
        # the information on the phi-function. We also store whether it
        # is reachable or not (true or false)
        self.virtual_copies: Set[Tuple[var_id_T, bool]] = None

        # Position of VGETs s.t. it corresponds to the last use according
        # to the dominator tree
        self.last_use: Set[int] = set()

    @property
    def elements_to_fix(self) -> Iterable:
        return self.get_count.keys()

    def add_virtual_copy(self, v: var_id_T):
        """
        Introduces v as a virtual_copy that might need to be
        introduced in registers. We distinguish two cases: v is accessible at late(B)
        (and hence, we can just dup it to access) or not.
        """
        _, _, is_last = self.reachable.get(v, (None, None, None))

        last_accessible = bool(is_last)
        self.virtual_copies.add((v, last_accessible))

        # If it is not accessible in the last instruction,
        # we need to load the GET the instruction elsewhere
        if not last_accessible:
            self.get_count.update(v)

    def insert_dup_vset(self, var: var_id_T):
        """
        Inserts an instruction (probably a DUP-VSET).
        We have to update the information on the reachability

        TODO: more efficient implementation based on intervals
        """
        pos_introduced, dup_pos, is_last = self.reachable[var]
        self.greedy_ids.insert(pos_introduced, f"DUP-VSET({var},{dup_pos})")

        vars_to_update = self.reachable.keys()
        for var_ in vars_to_update:
            num_instr, dup_pos, is_last = self.reachable[var_]
            # Only update indexis from the old position
            if num_instr >= pos_introduced:
                self.reachable[var_] = num_instr + 1, dup_pos, is_last

    @classmethod
    def from_new_version(cls, greedy_ids: List[str], outcome: str, execution_time: float, original_instrs: List[instr_JSON_T],
                 get_count: Counter, elements_to_fix: Set[var_id_T], reachable: Dict[var_id_T, int]) -> 'GreedyInfo':
        return GreedyInfo(greedy_ids, outcome, execution_time, original_instrs)

    @classmethod
    def from_old_version(cls, greedy_ids: List[str], outcome: str,
                         execution_time: float, original_instrs: List[instr_JSON_T]):
        return GreedyInfo(greedy_ids, outcome, execution_time, original_instrs)
