from typing import Tuple
import networkx as nx


def compute_max_n_elements(node: str, instr_graph: nx.DiGraph()) -> Tuple[int, bool]:
    """
    Computes the maximum number of elements that can be used to fix a position
    """
    if instr_graph.out_degree(node) == 0:
        return 1, True

    # Commutative case
    if instr_graph.nodes[node]["commutative"]:
        edges = list(instr_graph.edges(node))
        first_arg_nodes, first_args_inserting = compute_max_n_elements(edges[0][1], instr_graph)
        second_arg_nodes, second_args_inserting = compute_max_n_elements(edges[1][1], instr_graph)

        # If one of them can insert elements
        if first_args_inserting or second_args_inserting:
            return first_args_inserting + second_args_inserting, False

        elif first_arg_nodes > second_arg_nodes:
            return first_arg_nodes, False

        else:
            return second_arg_nodes, False

    # Non-Commutative case
    else:
        n_elements = 0
        for edge in instr_graph.edges(node):
            target = edge[1]
            current_nodes, keep_on_inserting = compute_max_n_elements(target, instr_graph)
            n_elements += current_nodes
            if not keep_on_inserting:
                return n_elements, False

        return n_elements, False
