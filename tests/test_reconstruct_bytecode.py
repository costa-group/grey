import os
from argparse import Namespace
from execution.main_execution import main


class TestReconstructBytecode:

    def test_pushimmutable_assignimmutable(self):
        """
        20/01/2025: the code generation failed because PUSHIMMUTABLE can be followed by a string that is not
        a hexadecimal value and ASSIGNIMMUTABLE must assign only the first builtin args.

        Solution: for PUSHIMMUTABLE, define the function "to_hex_default" in solution_generation.utils, which returns
        the corresponding hexadecimal if the value a decimal value. Otherwise, it returns the original code.
        For ASSIGNIMMUTABLE, introduce the first builtin arg (if any) when reconstructing the split bytecode

        """
        # Args
        # -s examples/test/semanticTests/abiEncoderV1_struct_struct_storage_ptr/struct_storage_ptr_standard_input.json -g -v -if standard-json -o falla -solc ./solc-latest
        current_path = os.path.abspath(os.curdir)
        os.chdir("..")
        args = Namespace(
            source='tests/reconstruct_bytecode/pushimmutable_assignimmutable.json',
            input_format='standard-json', contract=None, solc_executable='./solc-latest', folder='falla',
            visualize=True, greedy=True, builtin=False)
        main(args)
        os.chdir(current_path)
        assert True, "Falla test"
