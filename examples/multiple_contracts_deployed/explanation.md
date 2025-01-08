# Contract: multiple_contracts.sol

## Why it is interesting:

In this example, we can analyze the structure of an assembly file. For contract `D`, we create one instance of other the other two contracts and operate with them. The problem is the deployment code for contract `C` does not appear in the current representation, due to its nested nature (see yul file).

# Fix:

Waiting for the yul exporter to be adapted to the current representation!