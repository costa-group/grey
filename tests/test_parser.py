import pytest
from parser.cfg import CFGBlock


class TestCFG:

    def test_cfg_creation(self):
        cfg_block = CFGBlock("ID", [], "Terminal", {})
        assert True
