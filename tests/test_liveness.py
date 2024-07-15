import logging
from parser.parser import parser_CFG_from_JSON
from liveness.liveness_analysis import perform_liveness_analysis


class TestAnalysis:

    def test_liveness_analysis_construction_if_yul(self):
        if_json = {"object": {"blocks": [{"exit": "Block0Exit", "id": "Block0",
                                          "instructions": [{"in": ["0x0101", "0x01"], "op": "sstore", "out": []},
                                                           {"in": ["0x00"], "op": "calldataload", "out": ["_27"]}],
                                          "type": "BuiltinCall"},
                                         {"cond": ["_27"], "exit": ["Block1", "Block2"], "id": "Block0Exit",
                                          "instructions": [],
                                          "type": "ConditionalJump"},
                                         {"exit": "Block1Exit", "id": "Block1", "instructions": [
                                             {"in": ["0x03", "0x03"], "op": "sstore", "out": []}],
                                          "type": "BuiltinCall"},
                                         {"exit": ["Block1"], "id": "Block1Exit", "instructions": [],
                                          "type": "MainExit"},
                                         {"exit": "Block2Exit", "id": "Block2",
                                          "instructions": [{"in": ["0x0202", "0x02"], "op": "sstore", "out": []}],
                                          "type": "BuiltinCall"},
                                         {"exit": ["Block1"], "id": "Block2Exit", "instructions": [], "type": "Jump"}],
                              "functions": {}}, "subObjects": {}, "type": "Object"}
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        if_cfg = parser_CFG_from_JSON(if_json)
        liveness_result = perform_liveness_analysis(if_cfg)
        logging.debug(liveness_result)
        assert len(liveness_result) > 0
