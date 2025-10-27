import pytest
import networkx as nx
from graphs.algorithms import compute_dominance_tree
from graphs.cfg import compute_loop_nesting_forest_graph


class TestGreedyNewVersion:

    def test_compute_loop_nesting_forest_graph(self):
        """
        From Fig 4.5 in Page 50
        """
        cfg = nx.DiGraph()
        edges = [
            (1, 2), (2, 3), (2, 7), (3, 4), (3, 5), (4, 6), (5, 6), (6, 8),
            (7, 8), (8, 9), (9, 10), (9, 11), (10, 11), (11, 9), (11, 12), (12, 2)
        ]
        cfg.add_edges_from(edges)
        # nx.nx_agraph.write_dot(cfg, "../cfg.dot")

        loop_forest = compute_loop_nesting_forest_graph(cfg)
        # nx.nx_agraph.write_dot(loop_forest, "../loop_forest.dot")

        expected_forest = nx.DiGraph()
        expected_edges = [
            (2, 3), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (2, 12),
            (9, 10), (9, 11)
        ]
        expected_forest.add_edges_from(expected_edges)
        assert set(loop_forest.edges) == set(expected_forest.edges), "The expected forest is not the expected"
