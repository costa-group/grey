from typing import Tuple, List
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
        # Ensure every path can be computed
        # TODO: improve strategy
        return min(first_arg_nodes, second_arg_nodes), False

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


def compute_preffix_computation(node: str, instr_graph: nx.DiGraph, instr_ids) -> Tuple[List[List[str]], bool]:
    if instr_graph.out_degree(node) == 0:
        return [[node]], True

    # Commutative case
    if instr_graph.nodes[node]["commutative"]:
        edges = list(instr_graph.edges(node))
        possibilities_first, first_args_inserting = compute_preffix_computation(edges[0][1], instr_graph, instr_ids)
        possibilites_second, second_args_inserting = compute_preffix_computation(edges[1][1], instr_graph, instr_ids)

        combined_possibilities = []
        if first_args_inserting:
            combined_possibilities += [first_possibility + second_possibility
                                       for first_possibility in possibilities_first
                                       for second_possibility in possibilites_second]
        else:
            combined_possibilities += possibilities_first

        if second_args_inserting:
            combined_possibilities += [second_possibility + first_possibility
                                       for second_possibility in possibilites_second
                                       for first_possibility in possibilities_first]
        else:
            combined_possibilities += possibilites_second

        return combined_possibilities, False

    # Non-Commutative case
    else:
        current_possibility = [[]]
        for edge in instr_graph.edges(node):
            target = edge[1]
            current_nodes, keep_on_inserting = compute_preffix_computation(target, instr_graph, instr_ids)
            current_possibility = [possibility + extension for possibility in current_possibility
                                   for extension in current_nodes]

            if not keep_on_inserting:
                return current_possibility, False

        return current_possibility, False
