from parser.cfg_block import CFGBlock
from parser.cfg_instruction import CFGInstruction
from liveness.stack_layout_methods import (block_events, tiers_order, h1_order, simulated_junk_layout,
                                           output_stack_layout)


def order_by_name(variables):
    """
    Deterministic order for the tests (top first)
    """
    return sorted(variables)


class TestJunkBottom:

    def test_block_events(self):
        # v2 = add(v0, v1); v3 = mul(v2, v1): v0 and v2 die, v1 is live at the exit
        block = CFGBlock("b", [CFGInstruction("add", ["v1", "v0"], ["v2"]),
                               CFGInstruction("mul", ["v1", "v2"], ["v3"])], "terminal", dict())
        events = block_events(block, {"v1", "v3"})
        assert events == [("last_use", "v0"), ("use", "v1"), ("produce", "v2"),
                          ("last_use", "v2"), ("use", "v1"), ("produce", "v3")]

    def test_hole_paired_with_new_value(self):
        # Input [v0, v1, v2] (top first): v1 dies after v3 is produced, so v3 takes its position
        events = [("produce", "v3"), ("last_use", "v1")]
        output, junk_idx = simulated_junk_layout(["v0", "v1", "v2"], [], {"v0", "v2", "v3"}, {},
                                                 events, order_by_name)
        assert output == ["v0", "v3", "v2"]
        assert junk_idx == 3

    def test_unfillable_holes_become_junk(self):
        # Input [v0, v1, v2, v3] (top first): v1, v2 and v3 are dead on entry (unfillable holes), so the junk
        # starts below v0 and nothing needs to be popped
        output, junk_idx = simulated_junk_layout(["v0", "v1", "v2", "v3"], [], {"v0"}, {}, [], order_by_name)
        assert output[:junk_idx] == ["v0"]
        assert output[junk_idx:] == ["v1", "v2", "v3"]

    def test_invalidated_variable_placed_on_top(self):
        # Input [v0, h1, h2, h3, v4] (top first) with three unfillable holes above v4: invalidating v4 (cost 1)
        # is cheaper than keeping three holes (cost 6), so v4 is placed again on top
        output, junk_idx = simulated_junk_layout(["v0", "h1", "h2", "h3", "v4"], [], {"v0", "v4"}, {},
                                                 [], order_by_name)
        assert output[:junk_idx] == ["v4", "v0"]
        assert output[junk_idx:] == ["h1", "h2", "h3", "v4"]

    def test_paired_hole_below_boundary_is_unpaired(self):
        # The new value v5 is paired with the hole of v3, but the junk starts above it: v5 goes on top
        events = [("produce", "v5"), ("last_use", "v3")]
        output, junk_idx = simulated_junk_layout(["v0", "h1", "h2", "v3"], [], {"v0", "v5"}, {},
                                                 events, order_by_name)
        live_part = output[:junk_idx]
        assert "v5" in live_part and "v0" in live_part

    def test_tiers_order(self):
        # The successor consumes v1 and then v0 first; v2 remains live after it and v3 dies later on
        successor_events = [("last_use", "v1"), ("last_use", "v0"), ("produce", "v4"), ("last_use", "v3")]
        order = tiers_order({"v0", "v1", "v2", "v3"}, {}, successor_events, {"v2"})
        assert order == ["v1", "v0", "v2", "v3"]

    def test_default_strategy_unchanged(self):
        # The default strategy and order produce the same layout as the h1 order passed explicitly
        input_stack, live = ["v0", "v1", "v2", "v3"], {"v0", "v2", "v4", "v5"}
        depth = {"v4": (1, 0, 0), "v5": (2, 0, 0)}
        default = output_stack_layout(input_stack, [], live, depth, True)
        explicit = output_stack_layout(input_stack, [], live, depth, True, "current", None,
                                       lambda variables: h1_order(variables, depth))
        assert default == explicit
