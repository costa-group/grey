"""
Module that implements an AbstractState and an AbstractAnalysisInfo in order to perform the
fixpoint analysis.
"""

from typing import Any, Iterable, List
from abc import ABC, abstractmethod
import networkx as nx
from parser.cfg_instruction import CFGInstruction


class AbstractBlockInfo(ABC):
    """
    Class that contains the information from the program needed to perform the corresponding analysis.
    Includes information about the CFG
    """

    @property
    @abstractmethod
    def block_id(self) -> Any:
        raise NotImplementedError

    @property
    @abstractmethod
    def successors(self) -> Iterable:
        raise NotImplementedError

    @property
    @abstractmethod
    def comes_from(self) -> Iterable:
        raise NotImplementedError

    @property
    @abstractmethod
    def block_type(self) -> Any:
        raise NotImplementedError

    @property
    @abstractmethod
    def instructions(self) -> List[CFGInstruction]:
        raise NotImplementedError


def digraph_from_block_info(block_info: Iterable[AbstractBlockInfo]) -> nx.DiGraph:
    """
    Generates a DiGraph considering the information from successors
    """
    graph = nx.DiGraph()
    for block in block_info:
        graph.add_node(block.block_id)
        for successor in block.successors:
            graph.add_edge(block.block_id, successor)
    return graph


class AbstractState(ABC):
    """
    Class that contains the methods needed in the state of the corresponding analysis
    """

    def __init__(self):
        pass

    @abstractmethod
    def lub(self, state: 'AbstractState') -> None:
        raise NotImplementedError

    @abstractmethod
    def leq(self, state: 'AbstractState') -> bool:
        raise NotImplementedError
