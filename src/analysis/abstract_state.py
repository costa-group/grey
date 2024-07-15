"""
Module that implements an AbstractState and an AbstractAnalysisInfo in order to perform the
fixpoint analysis.
"""

from typing import Any
from abc import ABC, abstractmethod


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
    def jumps_to(self) -> Any:
        raise NotImplementedError

    @property
    @abstractmethod
    def falls_to(self) -> Any:
        raise NotImplementedError

    @property
    @abstractmethod
    def block_type(self) -> Any:
        raise NotImplementedError


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
