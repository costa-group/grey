"""
Utils for cfg methods
"""
from typing import Dict, TypeVar
from global_params.types import block_list_id_T

T = TypeVar('T')


def union_find_search(element: T, element2element: Dict[T, T]) -> T:
    """
    Following the idea of a union-find, determine which is to which block
    list the current block is associated
    """
    next_block_list = element2element.get(element, element)
    if next_block_list == element:
        return element
    else:
        answer_block_list = union_find_search(next_block_list, element2element)
        element2element[element] = answer_block_list
        return answer_block_list
