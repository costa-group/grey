"""
Module with the general methods to perform actions in a CFGBlockList
"""
import abc


def duplicate_node(current_node: str) -> str:
    """
    Given a node, generates a new name for the second half of the node
    """
    split_name = current_node.split("_")
    if len(split_name) > 1:
        split_name[1] = str(int(split_name[1]) + 1)
        return '_'.join(split_name)
    else:
        return current_node + "_1"


class BlockAction(metaclass=abc.ABCMeta):
    """
    Interface that represents the different actions that can be performed over a block
    """

    @abc.abstractmethod
    def perform_action(self):
        raise NotImplementedError

    @abc.abstractmethod
    def __str__(self):
        raise NotImplementedError

    def __repr__(self):
        return self.__str__()
