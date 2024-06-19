from typing import List

class CFGInstruction:
    def __init__(self, op : str, in_args: List[str], out_args: List[str]):
        self.op = op
        self.in_args = in_args
        self.out_args = out_args
        self.builtin_args = None
        
    def set_builtin_args(self, builtin: List[str]) -> None:
        self.builtin_args = builtin
