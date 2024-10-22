from hypothesis import strategies as st
from parser.cfg_instruction import CFGInstruction


@st.composite
def cfg_instruction_list(draw, min_value: int, max_value: int):
    """
    Strategy to generate a list of n in (min_size, max_size) CFG instructions
    with distinct output variables for each block
    """
    n = draw(st.integers(min_value, max_value))
    ops = draw(st.lists(st.text(min_size=3, max_size=5), min_size=n, max_size=n))

    outs_already = set()
    outs = []
    for i in range(n):
        out_args = draw(st.lists(st.text(min_size=3, max_size=5).filter(lambda x: x not in outs_already),
                        min_size=0, max_size=1))
        outs_already.update(set(out_args))
        outs.append(out_args)

    ins = draw(st.lists(st.lists(st.text(min_size=3, max_size=5), min_size=0, max_size=2), min_size=n, max_size=n))
    return [CFGInstruction(op, in_arg, out_arg) for op, in_arg, out_arg in zip(ops, ins, outs)]
