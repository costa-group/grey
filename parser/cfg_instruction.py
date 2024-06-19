from typing import List

class CFGInstruction:
    def __init__(self, op : str, in_args: List[str], out_args: List[str]):
        self.op = op
        self.in_args = in_args
        self.out_args = out_args
        self.builtin_args = None
        
    def set_builtin_args(self, builtin: List[str]) -> None:
        self.builtin_args = builtin


    def get_as_json(self):
        instruction = {}

        instruction["in"] = self.in_args
        instruction["out"] = self. out_args
        instruction["op"] = self.op

        if self.builtin_args == None:
            instruction["builtinArgs"] = self.builtin_agrs

        return instruction

    def get_out_args(self):
        return self.out_args
    
    def __str__(self):
        self.get_as_json()
