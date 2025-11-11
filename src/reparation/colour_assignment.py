"""
Module with the class needed to perform
the colour assignment
"""
from global_params.types import var_id_T, block_id_T
from typing import List, Dict, Tuple, Set, Optional
from reparation.phi_webs import PhiWebs


class ColourAssignment:
    """
    Class that stores the information for colouring variables
    """
    def __init__(self):
        self._total_colors: int = 0

        # We determine which variable is associated to a colour
        self._var2color: Dict[block_id_T, int] = dict()

    @property
    def num_colors(self) -> int:
        return self._total_colors

    @property
    def num_regs(self) -> int:
        return len(set(self._var2color.values()))

    @property
    def num_assigned(self):
        return len(self._var2color)

    def pick_available_colour(self, v: var_id_T, available: List[bool]) -> int:
        """
        Chooses an available colour, adding a new one if there are not enough
        """
        i = 0
        found_colour = False
        while not found_colour and i < len(available):
            if available[i]:
                available[i] = False
                found_colour = True
                self._var2color[v] = i
            else:
                i += 1

        # If all colours are used, we need to increase the number of colours
        if not found_colour:
            new_color = len(available)
            available.append(False)
            self._var2color[v] = new_color
            # Update the number of colours (might not be initialized
            # for other cases)
            self._total_colors = max(self._total_colors, new_color + 1)
            return new_color
        return i

    def pick_specific_colour(self, v: var_id_T, available: List[bool], color: int):
        """
        Picks a specific colour
        """
        # This might be a color for which current available
        # has no sufficient elements first. Hence, we extend it with false
        if len(available) <= color:
            available = available + [False] * (color - len(available) + 1)
        assert available[color], f"Picked color {color} for variable {v} is not available"
        available[color] = False
        self._var2color[v] = color

    def has_variable(self, v: var_id_T):
        return v in self._var2color

    def release_colour(self, v: var_id_T, available: List[bool]):
        print("RELEASING", v)
        available[self._var2color[v]] = True

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
