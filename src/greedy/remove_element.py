#!/usr/bin/env python3

import json
import os
import sys
import resource
from typing import List, Dict, Tuple, Any, Union, Set
import traceback
import itertools

output_stack_T = str
id_T = str
disasm_T = str

#  <-- Add list if not dependences (2 + i params)

def  delete_all(elem,stack):
    nstack = []
    ipos = []
    i = 0
    while i < len(stack):
        if stack[i] == elem:
            ipos.append(i)
        else:
            nstack.append(stack[i])
        i += 1
    return nstack, ipos

def get_op_position(e):
    if 'SWAP' in e:
        o = 'SWAP'
        p = int(e[4:])
    elif 'DUP' in e:
        o = 'DUP'
        p = int(e[3:])
    else:
        o = e
        p = 0
    return o, p

def trans_pos(p,positions_in_stack):
    n = 0
    for i in positions_in_stack:
        if i < p: n+=1
    return p-n
    
def recalculate(n,positions_in_stack):
    return list(map(lambda x: x+n, positions_in_stack))

def recalculate_and_remove(p,positions_in_stack):
    new_pos = []
    for r in positions_in_stack:
        if r < p:
            new_pos.append(r)
        elif r > p:
            new_pos.append(r-1)
    return new_pos

class SMSremove:

    def __init__(self, json_format):
        self._orig_opid = json_format['original_opid']
        self._initial_stack = json_format['src_ws']
        self._final_stack = json_format['tgt_ws']
        self._user_instr = json_format['user_instrs']
        self._to_remove = json_format['to_remove']
        self._var_instr_map = {}
        for ins in self._user_instr:
            if len(ins['outpt_sk']) == 1:
                self._var_instr_map[ins['outpt_sk'][0]] = ins
        self._opid_instr_map = {}
        for ins in self._user_instr:
            self._opid_instr_map[ins['id']] = ins
   
    def remove_element_list(self,instructions, stack, nstack, positions_in_stack):
        cstack = stack.copy()
        cnstack = nstack.copy()
        cpositions = positions_in_stack.copy()
        instr = instructions.copy()
        ninstr = []
        while len(instr) > 0:
            op = instr.pop(0)
            o, p = get_op_position(op)
            if o == 'SWAP':
                np = trans_pos(p,cpositions)
                if p not in cpositions:
                    no = 'SWAP' + str(np)
                    cstack = [cstack[p]] + cstack[1:p] + [cstack[0]] + cstack[p+1:]
                    cnstack = [cnstack[np]] + cnstack[1:np] + [cnstack[0]] + cnstack[np+1:]
                else:
                    assert(0 not in cpositions)
                    assert(np >= 0)
                    if np > 0 and len(instr) > 0:
                        assert(np - 1 <= 16)                    
                        swaps = []
                        for i in reversed(range(1, np)):
                            if cstack[0] != cstack[i]:
                                swaps += ['SWAP' + str(i)]
                                cnstack = [cnstack[i]] + cnstack[1:i] + [cnstack[0]] + cnstack[i + 1:]
                                if verbose: print('SWAP' + str(i), cnstack, cpositions)
                        if instr[0] != 'POP':
                            v = cstack[p]
                            ninstr += swaps
                            no = 'VGET(' + v + ')'
                            cstack = [cstack[p]] + cstack[1:p] + [cstack[0]] + cstack[p+1:]
                            cnstack = [v] + cnstack[1:np] + [cnstack[0]] + cnstack[np+1:]
                            cpositions.remove(p)
                        else:
                            instr.pop(0)
                            cstack = cstack[1:p] + [cstack[0]] + cstack[p+1:]
                            cpositions = recalculate_and_remove(p,cpositions)
                            continue
            elif o == 'DUP':
                if p-1 in cpositions:
                    v = cstack[p-1]
                    no = 'VGET(' + v + ')'
                    cstack = [v] + cstack
                    cnstack = [v] + cnstack
                else:
                    np = trans_pos(p-1,cpositions)+1
                    no = 'DUP' + str(np)
                    assert(cstack[p-1] == cnstack[np-1])
                    cstack = [cstack[p-1]] + cstack
                    cnstack = [cnstack[np-1]] + cnstack
                cpositions = recalculate(1,cpositions)
            elif o == 'POP':
                cstack.pop(0)
                cnstack.pop(0)
                if len(cpositions) > 0 and cpositions[0] == 0: cpositions.pop(0)
                cpositions = recalculate(-1,cpositions)
                no = o
            else:
                no = o
                inpt = self._opid_instr_map[o]['inpt_sk']
                for i in range(len(inpt)):
                    assert(i not in cpositions)
                outpt = self._opid_instr_map[o]['outpt_sk']
                if self._opid_instr_map[o]['commutative']:
                    assert(inpt == cstack[:len(inpt)] or [inpt[1],inpt[0]] == cstack[:len(inpt)])
                    assert(inpt == cnstack[:len(inpt)] or [inpt[1],inpt[0]] == cnstack[:len(inpt)])
                else:
                    assert(inpt == cstack[:len(inpt)])
                    assert(inpt == cnstack[:len(inpt)])
                cstack = outpt + cstack[len(inpt):]
                cnstack = outpt + cnstack[len(inpt):]
                cpositions = recalculate(len(outpt)-len(inpt),cpositions)
            ninstr.append(no)
            if verbose: print(no, cnstack, cpositions)
        return ninstr, cnstack

    def remove_element(self) -> Tuple[List[str], List[str], List[str]]:
        ini = self._initial_stack.copy()
        fin = self._final_stack.copy()
        ins = self._orig_opid.copy()
        for elem in self._to_remove:
            nini, ipos = delete_all(elem,ini)
            assert(ipos == sorted(ipos))
            nfin, _ = delete_all(elem,fin)
            ins, fin = self.remove_element_list(ins,ini,nini,ipos)
            assert(nfin == fin)
        return ins, ini, fin
        
def remove_from_json(json_data: Dict[str, Any], verb=True) -> Tuple[
    Dict[str, Any], SMSremove, List[str], List[str], List[str], int]:
    # print(encoding._var_instr_map)
    # print()
    # print(encoding._opid_instr_map)
    # print(encoding._mem_order)
    # print(encoding._sto_order)
    global verbose
    verbose = False # True # 
    encoding = SMSremove(json_data)
    try:
        ins, ini, fin = encoding.remove_element()
        error = 0
    except AssertionError:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb)
        print("Error")
        ins = None
        ini = None
        fin = None
        # print(name,encoding._b0,0 )
        error = 1
    return json_data, encoding, ins, ini, fin, error


def remove_standalone(sms: Dict) -> Tuple[str, float, List[str], List[str], List[str]]:
    """
    Executes the remove algorithm as a standalone configuration. Returns whether the execution has been
    sucessful or not ("non_optimal" or "error"), the total time and the sequence of ids, de initial stack 
    and final stack returned.
    """
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    try:
        json_info, ins, ini, fin, error = remove_from_json(sms)
        usage_stop = resource.getrusage(resource.RUSAGE_SELF)
    except Exception as e:
        print(str(e))
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb, file=sys.stdout)
        usage_stop = resource.getrusage(resource.RUSAGE_SELF)
        error = 1
        seq_ids = []
    remove_outcome = "error" if error == 1 else "removed"
    return remove_outcome, usage_stop.ru_utime + usage_stop.ru_stime - usage_start.ru_utime - usage_start.ru_stime, ins, ini, fin


def remove_from_file(filename: str):
    with open(filename, "r") as f:
        sfs = json.load(f)
    outcome, time, ins, ini, fin = remove_standalone(sfs)
    return sfs, ins, ini, fin, outcome


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        json_read = json.load(f)

    # minst = minsize_from_json(json_read)

    name = sys.argv[1]
    if '/' in name:
        p = len(name) - 1 - list(reversed(name)).index('/')
        name = name[p + 1:]

    json_info, encod, ins, ini, fin, error = remove_from_json(json_read)  # ,True) if verbose


    json_result = json.dumps(json_info)
    checker_name = ""
    output_name = ""
    if len(sys.argv) > 2:
        if os.path.isfile(sys.argv[2]):
            checker_name = sys.argv[2]
        else:
            output_name = sys.argv[2] + "/" + name
    if len(sys.argv) > 3:
        if checker_name == "":
            checker_name = sys.argv[3]
        else:
            output_name = sys.argv[3] + "/" + name
    if output_name != "":
        with open(output_name, 'w') as fw:
            fw.write(json_result)
    else:
        print(name, ins, ini, fin)
