"""
Module that contains useful methods for the liveness generation
"""
from typing import Dict, List
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
