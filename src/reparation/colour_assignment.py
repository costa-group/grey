"""
Module with the class needed to perform
the colour assignment
"""
from global_params.types import var_id_T
from typing import List, Dict, Optional, Set, Iterable

# For each colour, the value that currently owns it in the traversed path of the dominator
# tree (None if the colour is available)
owners_T = List[Optional[var_id_T]]


class ColourAssignment:
    """
    Class that stores the information for colouring variables. Every value is coloured exactly once
    (values stored in memory have a single definition, see reparation.memory_values)
    """
    def __init__(self):
        self._total_colors: int = 0

        # We determine which variable is associated to a colour
        self._var2color: Dict[var_id_T, int] = dict()

    @property
    def num_colors(self) -> int:
        return self._total_colors

    @property
    def num_regs(self) -> int:
        return len(set(self._var2color.values()))

    @property
    def num_memory_slots(self) -> int:
        """
        Number of memory slots reserved, i.e. the highest colour used plus one. Differs from
        num_regs when some intermediate colour ends up with no variable assigned
        """
        return max(self._var2color.values(), default=-1) + 1

    @property
    def num_assigned(self):
        return len(self._var2color)

    def next_constant(self, constants: List[str]) -> str:
        return constants[max(self._var2color.values())]

    def _assign(self, v: var_id_T, owners: owners_T, colour: int) -> None:
        assert v not in self._var2color, f"Value {v} is coloured twice"
        owners[colour] = v
        self._var2color[v] = colour
        self._total_colors = max(self._total_colors, colour + 1)

    def pick_available_colour(self, v: var_id_T, owners: owners_T, forbidden: Iterable[int] = ()) -> int:
        """
        Chooses the first available colour that is not forbidden, adding a new one if there are not enough
        """
        forbidden = set(forbidden)
        for colour, owner in enumerate(owners):
            if owner is None and colour not in forbidden:
                self._assign(v, owners, colour)
                return colour

        # If all colours are used, we need to increase the number of colours
        new_colour = len(owners)
        while new_colour in forbidden:
            owners.append(None)
            new_colour += 1
        owners.append(None)
        self._assign(v, owners, new_colour)
        return new_colour

    def is_available(self, colour: int, owners: owners_T) -> bool:
        return colour >= len(owners) or owners[colour] is None

    def pick_specific_colour(self, v: var_id_T, owners: owners_T, colour: int) -> None:
        """
        Picks a specific colour, which must be available
        """
        assert self.is_available(colour, owners), f"Picked color {colour} for variable {v} is not available"
        while len(owners) <= colour:
            owners.append(None)
        self._assign(v, owners, colour)

    def has_variable(self, v: var_id_T):
        return v in self._var2color

    def release_colour(self, v: var_id_T, owners: owners_T) -> None:
        """
        Releases the colour of v, only if v still owns it in the current path
        """
        colour = self._var2color.get(v)
        if colour is not None and colour < len(owners) and owners[colour] == v:
            owners[colour] = None

    def release_dead(self, owners: owners_T, live: Set[var_id_T]) -> None:
        """
        Releases the colours of the values that are not live
        """
        for colour, owner in enumerate(owners):
            if owner is not None and owner not in live:
                owners[colour] = None

    def is_coloured(self, var_: var_id_T):
        return var_ in self._var2color

    def color(self, var_: var_id_T) -> Optional[int]:
        return self._var2color.get(var_)
