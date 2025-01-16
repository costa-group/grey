split_block = {'calldatacopy', 'create', 'codecopy', 'call', 'log4', 'gas', 'delegatecall', 'extcodecopy', 'create2',
               'assignimmutable', 'returndatacopy', 'log2', 'log1', 'log3', 'log0', 'datacopy', 'staticcall','tstore','tload'}

terminal_ops = {"functionReturn", "functionReturn", "return", "revert"}

# split_block = {"ASSIGNIMMUTABLE", "GAS", "MEMORYGUARD", "DATACOPY"}

def add_verbatim_to_split_block(verbatim_inst):
    split_block.add(verbatim_inst)
