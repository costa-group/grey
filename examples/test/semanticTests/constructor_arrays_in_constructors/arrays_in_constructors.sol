contract Base {
    uint public m_x;
    address[] m_s;
    constructor(uint x, address[] memory s) {
        m_x = x;
        m_s = s;
    }
    function part(uint i) public returns (address) {
        return m_s[i];
    }
}
contract Main is Base {
    constructor(address[] memory s, uint x) Base(x, f(s)) {}
    function f(address[] memory s) public returns (address[] memory) {
        return s;
    }
}
contract Creator {
    function f(uint x, address[] memory s) public returns (uint r, address ch) {
        Main c = new Main(s, x);
        r = c.m_x();
        ch = c.part(x);
    }
}
// ====
// bytecodeFormat: legacy,>=EOFv1
// ----
// f(uint256,address[]): 7, 0x40, 10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 -> 7, 8
// gas irOptimized: 327784
// gas irOptimized code: 94000
// gas legacy: 336623
// gas legacy code: 244800
// gas legacyOptimized: 329515
// gas legacyOptimized code: 117000
