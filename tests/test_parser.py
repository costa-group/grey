import pytest
from typing import Dict
from parser.cfg_block import CFGBlock
from parser.cfg_instruction import build_instr_spec, build_verbatim_spec, build_push_spec, CFGInstruction

class TestCFG:

    def test_cfg_creation(self):
        cfg_block = CFGBlock("ID", [], "Terminal", {})
        assert True


def compare_sfs_json(expected_sfs_json: Dict, generated_sfs_json: Dict):
    for key in expected_sfs_json:
        assert key in generated_sfs_json, f"Key {key} not found in verbatim json"
        assert generated_sfs_json[key] == expected_sfs_json[key], \
            f"Different values for sfs json. Expected: {expected_sfs_json[key]} Generated: {generated_sfs_json[key]}"


class TestCFGInstruction:

    def test_build_push_spec(self):
        assert True

    def test_build_verbatim_spec_direct(self):
        verbatim_cfg_json = {
            "builtinArgs": [
              "50505050505050505050"
            ],
            "in": [
              "_77",
              "_78",
              "_79",
              "_80",
              "_81",
              "_82",
              "_83",
              "_84",
              "_85",
              "_86"
            ],
            "op": "verbatim_10i_0o",
            "out": []
          }

        # Define the fields we expect to obtain from the json
        expected_sfs_json = {
            'id': 'verbatim_10i_0o_args_50505050505050505050',
            'opcode': '50505050505050505050',
            'disasm': '50505050505050505050',
            'inpt_sk': ['_86', '_85', '_84', '_83', '_82', '_81', '_80', '_79', '_78', '_77'],
            'outpt_sk': [], 'commutative': False, 'push': False, 'storage': True, 'size': 10
        }

        generated_sfs_json = build_verbatim_spec(verbatim_cfg_json["op"], list(reversed(verbatim_cfg_json["in"])),
                                                 verbatim_cfg_json["out"], verbatim_cfg_json["builtinArgs"])

        compare_sfs_json(expected_sfs_json, generated_sfs_json)

    def test_build_verbatim_spec_from_cfg(self):
        verbatim_cfg_json = {
            "builtinArgs": [
              "50505050505050505050"
            ],
            "in": [
              "_77",
              "_78",
              "_79",
              "_80",
              "_81",
              "_82",
              "_83",
              "_84",
              "_85",
              "_86"
            ],
            "op": "verbatim_10i_0o",
            "out": []
          }
        expected_sfs_json = {
            'id': 'VERBATIM_10I_0O_args_50505050505050505050',
            'opcode': '50505050505050505050',
            'disasm': '50505050505050505050',
            'inpt_sk': ['_86', '_85', '_84', '_83', '_82', '_81', '_80', '_79', '_78', '_77'],
            'outpt_sk': [], 'commutative': False, 'push': False, 'storage': True, 'size': 10
        }

        cfg_instr = CFGInstruction(verbatim_cfg_json["op"], verbatim_cfg_json["in"], verbatim_cfg_json["out"])
        cfg_instr.builtin_args = verbatim_cfg_json["builtinArgs"]

        generated_sfs_json, new_out = cfg_instr.build_spec('0', dict(), dict())
        compare_sfs_json(expected_sfs_json, generated_sfs_json[0])

    def test_build_instr_spec(self):
        assert True
