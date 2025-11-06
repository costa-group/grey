"""
Class for representing the atomic_merged_set, a data structure
that keeps which elements must be assigned the same colour
"""
from typing import Dict, List, Optional, Set, Iterable
from global_params.types import var_id_T
from collections import defaultdict


class PhiWebs:
    """
    Data structure based on Union-Find that combines
    all interference values in a single class
    """

    def __init__(self):
        self._var2class: Dict[var_id_T, int] = dict()
        self._class2parent: List[int] = []
        self._n_elems_class: List[int] = []
        self._rank: List[int] = []
        self._num_sets = 0

    def initialize_element(self, var_: var_id_T):
        if var_ not in self._var2class:
            index = len(self._class2parent)
            self._var2class[var_] = index
            self._class2parent.append(index)
            self._n_elems_class.append(1)
            self._rank.append(0)
            self._num_sets += 1

    def is_in_some_set(self, var_: var_id_T):
        return var_ in self._var2class

    @property
    def num_sets(self):
        return self._num_sets

    @property
    def num_elements(self):
        return len(self._var2class)

    @property
    def classes_with_elements(self) -> Set[int]:
        """
        Returns for which classes there are elements that belong to that class
        """
        return set(class_number for class_number, num_elems
                   in enumerate(self._n_elems_class) if num_elems > 0)

    def _find_index(self, index: int) -> int:
        if self._class2parent[index] != index:
            self._class2parent[index] = self._find_index(self._class2parent[index])
        return self._class2parent[index]

    def find_set(self, var_: var_id_T) -> int:
        return self._find_index(self._var2class[var_])

    def union_set(self, var1: var_id_T, var2: var_id_T):
        class1, class2 = self.find_set(var1), self.find_set(var2)
        if class1 != class2:
            if self._rank[class1] > self._rank[class2]:
                self._class2parent[class2] = class1
                self._n_elems_class[class1] += self._n_elems_class[class2]
                self._n_elems_class[class2] = 0
            else:
                self._class2parent[class1] = class2
                self._n_elems_class[class2] += self._n_elems_class[class1]
                self._n_elems_class[class1] = 0

                if self._rank[class1] == self._rank[class2]:
                    self._rank[class2] += 1

            self._num_sets -= 1

    def join_phi(self, phi_def: var_id_T, phi_values: Set[var_id_T]):
        self.initialize_element(phi_def)
        for phi_value in phi_values:
            self.initialize_element(phi_value)
            self.union_set(phi_def, phi_value)

    def get_sets(self) -> List[Set[var_id_T]]:
        """
        Returns a list of disjoint sets, where each set contains
        the variables that belong to the same class.
        """
        sets_by_root: Dict[int, Set[var_id_T]] = defaultdict(set)

        for var, idx in self._var2class.items():
            root = self._find_index(idx)
            sets_by_root[root].add(var)

        return [set_ for set_ in sets_by_root.values() if len(set_) > 1]

    def has_element(self, var: var_id_T):
        """
        Needed to signal that an element has to be passed
        """
        return var in self._var2class
