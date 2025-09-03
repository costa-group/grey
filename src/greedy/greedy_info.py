"""
Module for computing relevant information from the greedy algorithm
"""
from typing import List, Set
from collections import Counter
from global_params.types import var_id_T


class GreedyInfo:

    def __init__(self, greedy_ids: List[str], outcome: str, execution_time: float,
                 get_count: Counter, elements_to_fix: Set[var_id_T], reachable: Set[var_id_T]):
        self.greedy_ids = greedy_ids
        self.outcome = outcome
        self.execution_time = execution_time
        self.get_count = get_count
        self.elements_to_fix = elements_to_fix
        self.reachable = reachable

    @classmethod
    def from_new_version(cls, greedy_ids: List[str], outcome: str, execution_time: float,
                 get_count: Counter, elements_to_fix: Set[var_id_T], reachable: Set[var_id_T]) -> 'GreedyInfo':
        return GreedyInfo(greedy_ids, outcome, execution_time, get_count, elements_to_fix, reachable)

    @classmethod
    def from_old_version(cls, greedy_ids: List[str], outcome: str, execution_time: float):
        return GreedyInfo(greedy_ids, outcome, execution_time, Counter(), set(), set())
