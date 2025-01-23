import pytest
import os
from argparse import Namespace
from execution.main_execution import main


class TestStructure:

    def test_nested_subcontracts(self):
        """
        21/01/2025: in the version of solc that was provided in 15/01/2024, the subObjects appear as part of the
        keys of a CFG Object (with "blocks" and "functions"). We have adapted the structure to fit this str

        Solution: We have adapted the structure to fit this structure.
        """
        # Args
        # -s tests/nested_subcontracts.sol -g -v -if sol -o prueba -solc ./solc-objects
        current_path = os.path.abspath(os.curdir)
        os.chdir("..")
        args = Namespace(
            source='tests/nested_subcontracts.sol',
            input_format='sol', contract=None, solc_executable='./solc-objects', folder='falla',
            visualize=True, greedy=True, builtin=False)
        main(args)
        os.chdir(current_path)
        assert True, "Falla test"