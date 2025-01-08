contract C {
    uint public x = msg.value - 10;
    constructor() payable {}
}

contract E {
    uint public x = msg.value - 10;
    constructor() payable {}
}

contract D {

    function g() public payable returns (uint) {
        return (new C{value: 11}()).x() + (new E{value: 12}()).x();
    }
}
// ----
// f() -> FAILURE, hex"4e487b71", 0x11
// g(), 100 wei -> 1
// gas legacy: 76780
// gas legacy code: 23600
