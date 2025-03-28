contract D {
    uint256 x;

    constructor() {
        x = 7;
    }

    function f() public view returns (uint256) {
        return x;
    }
}

contract C {
    function test() public returns (uint256) {
        D d = new D();
        bytes32 hash;
        assembly { hash := extcodehash(d) }
        assert(hash == keccak256(type(D).runtimeCode));
        return 42;
    }
}
// ====
// EVMVersion: >=constantinople
// bytecodeFormat: legacy
// ----
// test() -> 42
// gas legacy: 76034
// gas legacy code: 24200
