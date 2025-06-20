"""
Module that implements an alternative version the Tree Scan algorithm from
"SSA-based Compiler Design" (Page 309). The key difference is that we assume
an unbounded number of registers to colour, as the EVM memory can
grow indefinitely (although dangerously in cost...). Moreover, the liveness sets
are determined according to the last point in which a variable could be accessed
"""
import networkx as nx
from collections import defaultdict
from global_params.types import var_id_T, block_id_T
from typing import List, Dict, Tuple, Set, Optional
from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList


# First, we need to detect which program points must be stored at some point
# We use the information stored in greedy_ids, in some kind of post-order traversal
# (Algorithm 9.2 of "SSA-based Compiler Design").


def variable2block_header(cfg_block_list: CFGBlockList, forest_graph: nx.DiGraph) -> Dict[var_id_T, block_id_T]:
    """
    Determines which is the loop header of the outer loop in which the variable
    is defined. Useful for determining when we want to store the variable
    """
    var2header = dict()
    # We only consider blocks that appear as part of the forest graph
    for block_id in forest_graph.nodes:
        block = cfg_block_list.get_block(block_id)

        predecessors = forest_graph.predecessors(block_id)
        if len(predecessors) != 0:
            assert len(predecessors) == 1, "There can only be one predecessor in the forest graph"
            predecessor = predecessors[0]

            # We only consider the variables defined in the block
            # Thanks to SSA, they are defined only once
            for variable in block.declared_variables:
                # We link the variable with the block
                var2header[variable] = predecessor
    return var2header


def update_set_use_def_chain(var_id: var_id_T, block_id: block_id_T, negative_idx: int,
                             use_def_chain: Dict[var_id_T, Tuple[Optional[block_id_T], Optional[int],
                                                                 Optional[block_id_T], Optional[int]]]):
    # Here the use_def_chain should already contain the stored_id, as we only store
    # to later load.
    use_def = use_def_chain.get(var_id, None)
    assert use_def is not None, f"Trying to set {var_id} when it has not been used previously"
    use_def_chain[var_id] = (block_id, negative_idx, use_def[2], use_def[3])


def insert_store_in_regs(cfg_block: CFGBlock, vars_to_introduce: Set[var_id_T],
                         var2header: Dict[var_id_T, block_id_T], loop_forest: nx.DiGraph,
                         use_def_chain: Dict[var_id_T, Tuple[Optional[block_id_T], Optional[int],
                                                             Optional[block_id_T], Optional[int]]]) -> Set[var_id_T]:
    """
    Modifies the cfg_ids in cfg_block to store the variables in vars_to_introduce,
    considering the information from the var2header dict.
    """
    # We detect which values must be stored at some point according to the values
    for i, instruction_id in enumerate(reversed(cfg_block.greedy_ids)):
        if instruction_id.startswith("GET"):
            loaded_var = instruction_id[4:-1]

            # We add the var to introduce
            vars_to_introduce.add(loaded_var)

            # Afterwards, we need to introduce the position of the GET if it has not appeared yet.
            # The idea is to just store the deepest store
            # TODO: modify if we allow spilling
            use_def = use_def_chain.get(loaded_var, None)
            if use_def is None:
                use_def_chain[loaded_var] = (None, None, cfg_block.block_id, -i - 1)

        # Instructions are only set for solving permutation.
        # Hence, the corresponding values do not need to be propagated upwards
        elif instruction_id.startswith("SET"):
            stored_var = instruction_id[4:-1]
            vars_to_introduce.remove(stored_var)

            # We update the set info
            update_set_use_def_chain(stored_var, cfg_block.block_id, -i - 1, use_def_chain)

        # If the instruction defines a variable that is just accessible there, then we need to store it.
        else:
            # Global form to store multiple out vars if needed (not the case in the EVM)
            for out_var in cfg_block.out_vars_from_id(instruction_id):
                if out_var in vars_to_introduce:
                    index = len(cfg_block.greedy_ids) - i
                    cfg_block.greedy_ids.insert(index, f"DUP_SET({out_var})")

                    update_set_use_def_chain(out_var, cfg_block.block_id, index, use_def_chain)

    # Finally, we detect which values are accessible at the beginning of the block
    # so that we store them in memory. By applying this step at the beginning of the block,
    # we avoid repeating SETs for the same variable inside the block if it is loaded multiple times
    to_remove = set()
    for var_id in vars_to_introduce:

        # Two conditions must be satisfied: the variable can be accessed from the initial stack
        # and it is not inside a nested loop
        if cfg_block.is_accessible_in(var_id):
            header_loop = var2header.get(var_id, None)

            # We only store a variable if it is in the most possible outer loop
            if header_loop is not None and (
                    header_loop == cfg_block.block_id or loop_forest.has_edge(header_loop, cfg_block.block_id)):
                # We insert a DUP_SET instruction
                cfg_block.greedy_ids.insert(0, f"DUP_SET({var_id})")

                # We mark the variable for removal
                to_remove.add(var_id)

                # We update the
                update_set_use_def_chain(var_id, cfg_block.block_id, -len(cfg_block.greedy_ids), use_def_chain)

    return vars_to_introduce.difference(to_remove)


def dag_dfs_block(cfg_block: CFGBlock, cfg_block_list: CFGBlockList, traversed: Set[block_id_T],
                  var2header: Dict[var_id_T, block_id_T], loop_forest: nx.DiGraph,
                  use_def_chain: Dict[var_id_T, Tuple[Optional[block_id_T],
                  Optional[int], Optional[block_id_T], Optional[int]]]) -> Set[var_id_T]:
    """
    Post-order traversal of the CFG in order to generate the information on when to introduce the variables
    """
    vars_to_introduce = set()

    for block_id in cfg_block.successors:
        if block_id not in traversed:
            traversed.add(block_id)
            vars_to_introduce.update(dag_dfs_block(cfg_block_list.blocks[block_id], cfg_block_list,
                                                   traversed, var2header, loop_forest, use_def_chain))

    return insert_store_in_regs(cfg_block, vars_to_introduce, var2header, loop_forest, use_def_chain)


def dag_dfs(cfg_block_list: CFGBlockList, loop_forest: nx.DiGraph):
    # Use-def chain is a dict that links every variable to the deepest instance and the position in which it is
    # defined. It is used in the second traversal to remove SETs that are not needed
    use_def_chain: Dict[var_id_T, Tuple[Optional[block_id_T], Optional[int],
    Optional[block_id_T], Optional[int]]] = defaultdict(lambda: (None, None, None, None))
    var2header = variable2block_header(cfg_block_list, loop_forest)
    traversed = set()
    dag_dfs_block(cfg_block_list.get_block(cfg_block_list.start_block), cfg_block_list, traversed,
                  var2header, loop_forest, use_def_chain)


# Then, we colour the registers using the info from the previous stage


class ColourAssignment:
    """
    Class to represents the colouring of the graph.
    """

    def __init__(self):
        self._total_colors: int = 0
        self._used_colors: int = 0
        self._available: List = []

        # For each block, we have a dict that links all the variables that must be stored
        # in memory to the program point in which it must happen
        self._pp_store_color: Dict[block_id_T, Dict[var_id_T, int]] = defaultdict(lambda: dict())

        # We determine which variable is associated to a colour
        self._var2color: Dict[block_id_T, int] = dict()

    def pick_colour(self, v: var_id_T):
        """
        Chooses an available colour, adding a new one if there are not enough
        """
        # If all colours are used, we need to increase the number of colours
        if self._total_colors == self._used_colors:
            self._total_colors += 1
            self._used_colors += 1
            self._available.append(False)
            self._var2color[v] = self._total_colors - 1
        else:
            i = 0
            found_colour = False
            while not found_colour and i < self._total_colors:
                if self._available[i]:
                    self._available[i] = False
                    found_colour = True
                    self._used_colors += 1
                    self._var2color[v] = i
                else:
                    i += 1

            raise ValueError("There must exist a colour that has not been assigned so far")

    def release_colour(self, v: var_id_T):
        self._used_colors -= 1
        self._available[self._var2color[v]] = True


def assign_color(block: CFGBlock, block_list: CFGBlockList, cfg_order: nx.DiGraph):
    """
    We need to assign colours to each different block, following the cfg order.
    """
    pass


def tree_scan(block_list: CFGBlockList):
    """

    """
    pass
