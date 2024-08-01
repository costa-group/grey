"""
Module that contains useful methods for traversing nx.graphs
"""
from typing import Tuple, List, Dict, Any
import networkx as nx


def condense_to_dag(g: nx.Graph) -> Tuple[nx.DiGraph, List[List]]:
    """
    Given a graph g, returns another graph such that all the nodes that form a cycle in
    the original graph are condense into a single node.

    Returns
    -------
        dag: tuple
            a tuple with the directed graph that subsumes the new information and
            a list with the corresponding nodes in the original graph for each connected component
    """

    # Get the strongly connected components (SCCs)
    sccs = list(nx.strongly_connected_components(g))

    # Create a new directed graph for the DAG
    dag = nx.DiGraph()

    # Map each node to its SCC
    scc_map = {}
    for i, scc in enumerate(sccs):
        for node in scc:
            scc_map[node] = i

    # Add nodes to the DAG, each node represents an SCC
    dag.add_nodes_from(range(len(sccs)))

    # Add edges between SCCs to form the DAG
    for u, v in g.edges():
        if scc_map[u] != scc_map[v]:
            dag.add_edge(scc_map[u], scc_map[v])

    return dag, sccs


def information_on_graph(g: Any, new_name_dict: Dict[str, str]):
    """
    Generate a graph that includes the information stored in new_name_dict as nodes.
    Hence, it prints the corresponding information when the dot file is generated
    """
    renaming_dict = dict()
    for block_name, information_repr in new_name_dict.items():
        renaming_dict[block_name] = information_repr
    return nx.relabel_nodes(g, renaming_dict)
