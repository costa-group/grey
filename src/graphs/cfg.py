"""
Module for computing properties in the CFG
"""
import networkx as nx
from typing import List, Optional, Tuple

# Methods for generating the loop nesting forest


def find_back_edges(G: nx.DiGraph) -> List:
    """
    Compute all back edges in a directed graph G using DFS.
    Returns a list of (u, v) tuples that are back edges.
    """
    visited = set()
    rec_stack = set()
    back_edges = []

    def dfs(u):
        visited.add(u)
        rec_stack.add(u)
        for v in G.successors(u):
            if v not in visited:
                dfs(v)
            elif v in rec_stack:
                back_edges.append((u, v))
        rec_stack.remove(u)

    for node in G.nodes():
        if node not in visited:
            dfs(node)
    return back_edges


def find_natural_loop(cfg, u, v):
    """
    Compute the natural loop of back edge u -> v
    """
    loop_nodes = {v}
    worklist = [u]
    while worklist:
        n = worklist.pop()
        if n not in loop_nodes:
            loop_nodes.add(n)
            worklist.extend(cfg.predecessors(n))
    return loop_nodes


def compute_loop_nesting_forest_graph(cfg: nx.DiGraph, back_edges: Optional[List[Tuple]] = None):
    if back_edges is None:
        back_edges = find_back_edges(cfg)

    print("Back", back_edges)
    loops = []

    for u, v in back_edges:
        loop_nodes = find_natural_loop(cfg, u, v)
        loops.append((v, loop_nodes))  # v = loop header

    # Sort by size (smallest loops first)
    loops.sort(key=lambda x: len(x[1]))

    loop_bodies = {header: body for header, body in loops}
    headers = list(loop_bodies.keys())

    # Build nesting forest graph
    nesting_forest = nx.DiGraph()
    nesting_forest.add_nodes_from(headers)

    already_analyzed = set()
    for parent_header in headers:
        child_body = loop_bodies[parent_header]
        for child in child_body:
            # We ignore the header vertex to build the tree
            if child == parent_header:
                continue

            # We only add the child if it has not been added previously
            if child not in already_analyzed:
                already_analyzed.add(child)
                nesting_forest.add_edge(parent_header, child)

    return nesting_forest


def compute_cfg_without_backward_edges(cfg: nx.DiGraph) -> nx.DiGraph:
    back_edges = find_back_edges(cfg)
    new_cfg = cfg.copy()
    new_cfg.remove_edges_from(back_edges)
    return new_cfg
