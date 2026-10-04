"""
Loaded for the grey runs of this evaluation (PYTHONPATH=pyshim): this machine has no pygraphviz (nor the Graphviz
headers to build it), which grey only uses to write debug .dot graphs with --debug. Writing them becomes a no-op;
the checks of --debug are not affected.
"""
try:
    import pygraphviz  # noqa: F401
except ImportError:
    import networkx.drawing.nx_agraph as nx_agraph
    nx_agraph.write_dot = lambda graph, path: None
