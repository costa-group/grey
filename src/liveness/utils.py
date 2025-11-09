"""
Module that contains useful methods for the liveness generation
"""
from typing import Dict, List, Optional, Tuple
from parser.cfg import CFG
from global_params.types import component_name_T, var_id_T


def functions_inputs_from_components(cfg: CFG) -> Dict[component_name_T, List[var_id_T]]:
    """
    Generates a dict that contains the input parameters of all the objects and functions inside a cfg
    (excluding subObjects). The arguments are returned from the top to bottom
    """
    component2input_param = dict()
    for object_id, cfg_object in cfg.objectCFG.items():

        # CFG objects have empty arguments
        component2input_param[object_id] = []

        # We also consider the information per function
        for function_name, cfg_function in cfg_object.functions.items():
            component2input_param[function_name] = list(reversed(cfg_function.arguments))

    return component2input_param


def trim_none(l: List[Optional[str]]) -> Tuple[List[Optional[str]], int]:
    """
    Given a list of elements with None, returns the
    list with no None at the beginning and the sum of None elements afterwards
    """
    initial_not_none = 0
    while initial_not_none < len(l) and l[initial_not_none] is None:
        initial_not_none += 1

    final_list = l[initial_not_none:]
    return final_list, sum(1 for element in final_list if element is None)


def combine_lists_with_order(original_list: List[Optional[str]], second_list: List) -> List:
    """
    Merges the two lists so that None elements in the original list are replaced by
    the second list, starting with the bottom of both lists.
    """
    # Try to place the variables in reversed order
    i, j = len(original_list) - 1, len(second_list) - 1

    while i >= 0 and j >= 0:
        if original_list[i] is None:
            original_list[i] = second_list[j]
            j -= 1
        i -= 1

    # All variables have been placed in between. Hence, I have to insert the remaining
    # elements at the beginning
    return second_list[:j+1] + original_list


def find_longest_none_sequence(none_list: List[Optional[str]]) -> Tuple[int, int]:
    """
    Given a list with elements, possibly None, this methods finds a suffix
    s.t. # None elements - # other elements is maximized.
    TODO: decide tie which one is better
    """
    best_count, best_idx = 0, len(none_list)
    current_count, j = 0, len(none_list) - 1
    while j >= 0:
        current_count += 1 if none_list[j] is None else -1
        # For now, we just leave the
        if current_count > best_count:
            best_count = current_count
            best_idx = j
        j -= 1
    return best_idx, best_count


def merge_list_swapping_topmost(list_with_nones: List[Optional[str]]) -> List:
    """
    Given a lists, generates another list such that all None
    elements are replaced by other elements, swapping topmost elements
    to the bottom
    """
    i, j = 0, len(list_with_nones) - 1
    while i <= j:
        if list_with_nones[i] is None:
            i += 1
        elif list_with_nones[j] is None:
            list_with_nones[j] = list_with_nones[i]
            i += 1
            j -= 1
        else:
            j -= 1

    # All the None elements are before index i-1
    return list_with_nones[i:]


def combine_lists_with_junk(original_list: List[Optional[str]], second_list: List,
                            can_have_junk: bool) -> Tuple[List, int]:
    """
    Combines the original list with the elements from the second list, possibly generating junk
    in the process.
    """
    if can_have_junk:
        junk_idx, best_count = find_longest_none_sequence(original_list)
        junk_negative_idx = len(original_list) - junk_idx
        # We keep the elements emerged in the order found
        elements_to_emerge = [element for element in original_list[junk_idx:] if element is not None]

        # New bottom element
        new_bottom = original_list[:junk_idx]
    else:
        # Just keep the original list
        new_bottom = original_list
        elements_to_emerge = []
        junk_negative_idx = 0

    # We prioritize first emerging the elements that are too deep within the stack
    combined_list_with_possibly_nones = combine_lists_with_order(new_bottom, second_list + elements_to_emerge)

    # To ensure there are no Nones in between, we swap elements
    combined_list_without_nones = merge_list_swapping_topmost(combined_list_with_possibly_nones)

    # The result is the combination of the combined list and the junk elements decided initially
    return combined_list_without_nones, junk_negative_idx
