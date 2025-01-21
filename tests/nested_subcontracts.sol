contract C {
    uint public x = msg.value - 10;
    constructor() payable {}
}

contract E {
    uint public x = msg.value - 10;
    constructor() payable {
    	unchecked {
    		new C();
    }
}
}

contract D {
    function f() public {
        unchecked {
            new C();
        }
    }
}

contract F {
    function f() public {
        unchecked {
            new E();
            new D();
        }
    }
}
// ----
// f() -> FAILURE, hex"4e487b71", 0x11
// g(), 100 wei -> 1
// gas legacy: 76780
// gas legacy code: 23600
