"""
Module with the class needed to perform
the colour assignment
"""
from global_params.types import var_id_T, block_id_T
from typing import List, Dict, Tuple, Set, Optional


class ColourAssignment:
    """
    Class that stores the information for colouring variables
    """
    def __init__(self):
        self._total_colors: int = 0
        self._used_colors: int = 0

        # We determine which variable is associated to a colour
        self._var2color: Dict[block_id_T, int] = dict()

    @property
    def num_colors(self) -> int:
        return self._total_colors

    def pick_colour(self, v: var_id_T, available: List[bool]):
        """
        Chooses an available colour, adding a new one if there are not enough
        """
        # If all colours are used, we need to increase the number of colours
        if self._total_colors == self._used_colors:
            self._total_colors += 1
            self._used_colors += 1
            available.append(False)
            self._var2color[v] = self._total_colors - 1
        else:
            i = 0
            found_colour = False
            while not found_colour and i < self._total_colors:
                if available[i]:
                    available[i] = False
                    found_colour = True
                    self._used_colors += 1
                    self._var2color[v] = i
                else:
                    i += 1

            raise ValueError("There must exist a colour that has not been assigned so far")

    def has_variable(self, v: var_id_T):
        return v in self._var2color

    def release_colour(self, v: var_id_T, available: List[bool]):
        self._used_colors -= 1
        available[self._var2color[v]] = True

    def colour_set(self, var_set: Set[var_id_T]):
        """
        Colours all the elements in the set with a new color
        """
        for var_ in var_set:
            self._var2color[var_] = self._total_colors
        self._total_colors += 1
        self._used_colors += 1

    def uncolour_var(self, var_: var_id_T):
        """
        Uncolours one variable
        """
        # We assign the value -1 to uncolour
        self._var2color[var_] = -1

    def is_coloured(self, var_: var_id_T):
        return (colour := self._var2color.get(var_)) is not None and colour != -1

    def color(self, var_: var_id_T) -> Optional[int]:
        return self._var2color.get(var_)
