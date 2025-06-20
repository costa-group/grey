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
from graphs.cfg import compute_loop_nesting_forest_graph


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

def compute_var2blocks_used(block_list: CFGBlockList) -> Dict[var_id_T, Set[block_id_T]]:
    """
    For each variable that must be stored previously at some point, detects all the blocks
    in which it must be loaded because it is very deep
    """
    var2blocks_used = defaultdict(lambda: set())
    for block_id, block in block_list.blocks.items():
        for i, instruction_id in enumerate(reversed(block.greedy_ids)):
            # We only consider those var ids that are not directly dominated by a SET
            # (due to being set just inmediately)
            if instruction_id.startswith("GET"):
                loaded_var = instruction_id[4:-1]
                var2blocks_used[loaded_var].add(block_id)

            # If we have a SET, we just don't consider the variable for the first phase.
            elif instruction_id.startswith("SET"):

                loaded_var = instruction_id[4:-1]
                var2blocks_used[loaded_var].remove(block_id)

    return var2blocks_used

def compute_block2var_can_be_stored(dominance_tree: nx.DiGraph, var2blocks_used: Dict[var_id_T, Set[block_id_T]]) \
        -> Dict[block_id_T, List[var_id_T]]:
    """
    Finds the LCA (lowest common ancestor) in the dominance tree for all SETs for each variable.
    It is more useful for detecting from which block we can start considering a variable
    """
    lca_dict = dict(nx.tree_all_pairs_lowest_common_ancestor(dominance_tree))
    block2var_can_be_stored = defaultdict(lambda: [])
    for var_id, involved_blocks_set in var2blocks_used.items():
        involved_blocks = list(involved_blocks_set)
        lca_block = involved_blocks[0]
        for next_block in involved_blocks[1:]:
            # We don't know which option is represent: only one of them appears
            lca_block = first_option if (first_option := lca_dict.get((lca_block, next_block), None)) is not None else (
                lca_dict)[(next_block, lca_block)]
        block2var_can_be_stored[lca_block].append(var_id)

    return block2var_can_be_stored

def insert_store_in_regs(cfg_block: CFGBlock, vars_to_introduce: Set[var_id_T],
                         var2header: Dict[var_id_T, block_id_T], loop_forest: nx.DiGraph,
                         block2var_can_be_stored: Dict[block_id_T, List[var_id_T]]) -> Tuple[Set[var_id_T], Set[var_id_T]]:
    """
    Modifies the cfg_ids in cfg_block to store the variables in vars_to_introduce,
    considering the information from the var2header dict. It returns two sets:
    * 1) The stack variables that are allowed to be stored from the corresponding point (due to LCA)
    * 2) The stack variables being used in the current block
    """
    currently_used = set()

    # First, we see if there is some variable that must be
    # considered from this point on to be stored in a register
    vars_to_introduce.update(block2var_can_be_stored.get(cfg_block.block_id, set()))

    # We detect which values must be stored at some point according to the values
    for i, instruction_id in enumerate(reversed(cfg_block.greedy_ids)):
        if instruction_id.startswith("GET"):
            loaded_var = instruction_id[4:-1]

            # We add the variable to the set of variables currently being used
            currently_used.add(loaded_var)

        # Instructions are only set for solving permutation.
        # Hence, the corresponding values do not need to be propagated upwards
        elif instruction_id.startswith("SET"):
            stored_var = instruction_id[4:-1]

            # We only remove the stored var if it has not been removed before
            if stored_var in vars_to_introduce:
                vars_to_introduce.remove(stored_var)

        # If the instruction defines a variable that is just accessible there, then we need to store it.
        else:
            # Global form to store multiple out vars if needed (not the case in the EVM)
            for out_var in cfg_block.out_vars_from_id(instruction_id):
                if out_var in vars_to_introduce:
                    index = len(cfg_block.greedy_ids) - i
                    vars_to_introduce.remove(out_var)

                    cfg_block.greedy_ids.insert(index, f"DUP_SET({out_var})")

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

    return vars_to_introduce.difference(to_remove), currently_used


def dag_dfs_block(cfg_block: CFGBlock, cfg_block_list: CFGBlockList, traversed: Set[block_id_T],
                  var2header: Dict[var_id_T, block_id_T], loop_forest: nx.DiGraph,
                  block2var_can_be_stored: Dict[block_id_T, List[block_id_T]],
                  block2last_use: Dict[block_id_T, Set[block_id_T]]) -> Tuple[Set[var_id_T], Set[var_id_T]]:
    """
    Post-order traversal of the CFG in order to generate the information on when to introduce the variables
    """
    # Same sets as the previous functions
    vars_to_introduce, variables_used_children = set(), set()

    for block_id in cfg_block.successors:
        if block_id not in traversed:
            traversed.add(block_id)
            vars_to_introduce_child, variables_used_child = dag_dfs_block(cfg_block_list.blocks[block_id], cfg_block_list,
                                                                          traversed, var2header, loop_forest)
            vars_to_introduce.update(vars_to_introduce_child)
            variables_used_children.update(variables_used_child)

    (variables_to_introduce_current,
     variables_used) = insert_store_in_regs(cfg_block, vars_to_introduce, var2header,
                                                      loop_forest, block2var_can_be_stored)
    # We consider the variables used that are not used
    block2last_use[cfg_block.block_id] = variables_used.difference(variables_used_children)
    # We return the set of all variables used in the current branch
    variables_used_branch = variables_used.union(variables_used_children)

    # variables_introduced_current already considers the state from the children
    return variables_to_introduce_current, variables_used_branch


def dag_dfs(cfg_block_list: CFGBlockList, loop_forest: nx.DiGraph, dominance_tree: nx.DiGraph) -> Dict[block_id_T, Set[block_id_T]]:
    """
    Modifies the cfg_block_list inserting the needed SET instructions for registers in between, and
    returns the information for performing the tree scan.
    """

    # block2last_use maps each block to the set of variables
    # whose last use is the current block
    block2last_use = dict()

    # Var2header matches every variable to the header of the loop
    # in which it is being declared
    var2header = variable2block_header(cfg_block_list, loop_forest)
    traversed = set()

    # Var2blocks_used matches every time a variable is being loaded from memory
    # but it is not stored in the same block
    var2blocks_used = compute_var2blocks_used(cfg_block_list)

    # For each block, includes the variables that can be stored in registers from
    # that block upwards
    block2var_can_be_stored = compute_block2var_can_be_stored(dominance_tree, var2blocks_used)

    dag_dfs_block(cfg_block_list.get_block(cfg_block_list.start_block), cfg_block_list, traversed,
                  var2header, loop_forest, block2var_can_be_stored, block2last_use)
    return block2last_use

# Then, we colour the registers using the info from the previous stage (tree scan)


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


def assign_color(block: CFGBlock, block_list: CFGBlockList, dominance_tree: nx.DiGraph,
                 block2last_use: Dict[block_id_T, Set[var_id_T]],
                 colour_assignment: ColourAssignment) -> None:
    """
    We need to assign colours to each different block, following the cfg order.
    """
    block_id = block.block_id
    for variable in block2last_use[block_id]:
        colour_assignment.release_colour(variable)
    


def tree_scan_with_last_uses(block_list: CFGBlockList, dominance_tree: nx.DiGraph,
                             block2last_use: Dict[block_id_T, Set[var_id_T]]) -> ColourAssignment:
    """
    Adapted from Algorithm 22.1: Tree scan in page 309. Given the block list,
    and the list of program points, registers are assigned based on colours
    """
    colour_assignment = ColourAssignment()

    assign_color(block_list.get_block(block_list.start_block), dominance_tree, block2last_use, colour_assignment)
    return colour_assignment


# Full algorithm

def tree_scan(block_list: CFGBlockList, dominance_toposort: List[block_id_T], dominance_tree: nx.DiGraph) -> None:
    loop_forest = compute_loop_nesting_forest_graph(block_list, dominance_tree)
    block2last_use = dag_dfs(block_list, loop_forest, dominance_tree)
    tree_scan_with_program_points(block_list, dominance_toposort, block2last_use)
