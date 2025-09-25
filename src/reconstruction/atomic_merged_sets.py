"""
Class for representing the atomic_merged_set, a data structure
that keeps which elements must be assigned the same colour
"""
from typing import Dict, List, Optional, Set, Iterable
from global_params.types import var_id_T


class AtomicMergedSets:
    """
    Data structure that combines all atomic merged sets into
    a single object.
    """

    def __init__(self):
        self._var2class: Dict[var_id_T, int] = dict()
        self._class2vars: List[Set[var_id_T]] = []

    def add_set(self, var_set: Iterable[var_id_T]) -> None:
        # Assumes None of the elements are already assigned
        class_number = len(self._class2vars)
        for var in var_set:
            self._var2class[var] = class_number
        self._class2vars.append(set(var_set))

    def same_colour(self, variable: var_id_T) -> Optional[Set[var_id_T]]:
        """
        Returns the set of variables that are associated to the same resource
        """
        eq_class = self._var2class.get(variable)
        if eq_class is None:
            return None
        return self._class2vars[eq_class]
