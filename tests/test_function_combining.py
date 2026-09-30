from parser.cfg_block import CFGBlock
from parser.cfg_block_list import CFGBlockList
from parser.cfg_function import CFGFunction
from parser.cfg_instruction import CFGInstruction
from parser.cfg_object import CFGObject
from cfg_methods.function_combining import (combine_equivalent_functions_object, function_key,
                                            prune_unused_arguments_object)


def function(name, json_arguments, instructions, returned):
    """
    Single-block function: the instructions (JSON order of inputs) and then a return of the given values. The
    arguments are stored reversed, as the parser does
    """
    block_list = CFGBlockList(name)
    block = CFGBlock(f"{name}_Block0", instructions + [CFGInstruction("functionReturn", list(reversed(returned)), [])],
                     "FunctionReturn", dict())
    block_list.add_block(block)
    return CFGFunction(name, list(reversed(json_arguments)), [], block.block_id, block_list)


def call(name, inputs, outputs):
    """
    Call with its inputs in declaration order. solc's JSON lists them in stack order (reversed), and CFGInstruction
    reverses them again, so in_args ends up in declaration order
    """
    return CFGInstruction(name, list(reversed(inputs)), outputs)


def build_object():
    """
    main calls f, g, F, G, h, k and c:
      f(a, b) = add(a, b) and g(c, d) = add(c, d) are equivalent;
      F(x) = f(x, 1) and G(y) = g(y, 1) become equivalent once f and g are combined;
      c(a, b) = add(a, 2) differs in a constant;
      h(x, unused) = calldataload(x) and k(y) = calldataload(y) only differ in an unused argument
    """
    functions = [function("f", ["a", "b"], [CFGInstruction("add", ["a", "b"], ["r1"])], ["r1"]),
                 function("g", ["c", "d"], [CFGInstruction("add", ["c", "d"], ["r2"])], ["r2"]),
                 function("F", ["x"], [call("f", ["x", "0x01"], ["r3"])], ["r3"]),
                 function("G", ["y"], [call("g", ["y", "0x01"], ["r4"])], ["r4"]),
                 function("c", ["e", "u"], [CFGInstruction("add", ["e", "0x02"], ["r5"])], ["r5"]),
                 function("h", ["p", "q"], [CFGInstruction("calldataload", ["p"], ["r6"])], ["r6"]),
                 function("k", ["z"], [CFGInstruction("calldataload", ["z"], ["r7"])], ["r7"])]
    main_instructions = [call("f", ["0x01", "0x02"], ["m1"]), call("g", ["0x03", "0x04"], ["m2"]),
                         call("F", ["m1"], ["m3"]), call("G", ["m2"], ["m4"]), call("c", ["m3", "m4"], ["m5"]),
                         call("h", ["m5", "m4"], ["m6"]), call("k", ["m6"], ["m7"]), CFGInstruction("stop", [], [])]
    main_blocks = CFGBlockList("main")
    main_blocks.add_block(CFGBlock("main_Block0", main_instructions, "terminal", dict()))
    cfg_object = CFGObject("main", main_blocks)
    for cfg_function in functions:
        cfg_object.add_function(cfg_function)
    cfg_object.identify_function_calls_in_blocks()
    return cfg_object


def main_calls(cfg_object):
    return [(instruction.get_op_name(), list(instruction.get_in_args()))
            for instruction in cfg_object.blocks.get_block("main_Block0").get_instructions()
            if instruction.get_op_name() != "stop"]


class TestFunctionCombining:

    def test_keys(self):
        cfg_object = build_object()
        keys = {name: function_key(cfg_function) for name, cfg_function in cfg_object.functions.items()}
        assert keys["f"] == keys["g"]
        # Callees are compared by name, as in solc: F and G differ until f and g are combined
        assert keys["F"] != keys["G"]
        assert keys["c"] != keys["f"]
        assert keys["h"] != keys["k"]

    def test_combine_to_fixpoint(self):
        cfg_object = build_object()
        # f/g in the first round, F/G in the second one
        assert combine_equivalent_functions_object(cfg_object) == 2
        assert sorted(cfg_object.functions) == ["F", "c", "f", "h", "k"]
        calls = main_calls(cfg_object)
        assert calls[0] == ("f", ["0x01", "0x02"]) and calls[1] == ("f", ["0x03", "0x04"])
        assert calls[3] == ("F", ["m2"])
        assert "g" not in cfg_object.blocks.get_block("main_Block0").function_calls

    def test_prune_then_combine(self):
        cfg_object = build_object()
        # u in c and q in h are unused
        assert prune_unused_arguments_object(cfg_object) == 2
        assert list(reversed(cfg_object.functions["h"].arguments)) == ["p"]
        assert list(reversed(cfg_object.functions["c"].arguments)) == ["e"]
        calls = dict(main_calls(cfg_object))
        # The call keeps the used inputs in their positions
        assert calls["h"] == ["m5"] and calls["c"] == ["m3"]
        combine_equivalent_functions_object(cfg_object)
        assert "k" not in cfg_object.functions and "h" in cfg_object.functions
        assert [name for name, _ in main_calls(cfg_object)][-1] == "h"
