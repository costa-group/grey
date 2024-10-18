import logging
from execution.sol_compilation import SolidityCompilation


class TestSolCompilation:

    def test_simple_sol_yul(self):
        sol_compilation = SolidityCompilation.from_single_solidity_code("tests/files/simple_sol.sol", None,
                                                                        solc_executable="./solc-latest")
        assert len(sol_compilation) == 1, "It should return just one contract"
        contract_name = list(sol_compilation.keys())[0]
        contract_info = list(sol_compilation.values())[0]
        print(contract_name)
        assert contract_name == "tests/files/simple_sol.sol:Curta", \
            f"Expected name: tests/files/simple_sol.sol:Curta. Current name: {contract_name}"
        assert isinstance(contract_info, dict), "Expected type of value: dict"
