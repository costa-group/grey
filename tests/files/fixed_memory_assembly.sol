// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
// Inline assembly that is not memory-safe (fixed addresses above 0x80): solc emits no memoryguard
contract FixedMemory {
    function f(uint256 a, uint256 b, uint256 c, uint256 d, uint256 e, uint256 g) external pure returns (uint256 r) {
        assembly {
            mstore(0x80, a)
            mstore(0xa0, b)
        }
        uint256 x1 = a * b + c; uint256 x2 = b * c + d; uint256 x3 = c * d + e; uint256 x4 = d * e + g;
        uint256 x5 = e * g + a; uint256 x6 = g * a + b; uint256 x7 = x1 ^ x2; uint256 x8 = x3 ^ x4;
        uint256 x9 = x5 ^ x6;
        r = x1 + x2 * x3 + x4 * x5 + x6 * x7 + x8 * x9 + a * g;
        r = r ^ (x1 * x9 + x2 * x8 + x3 * x7 + x4 * x6);
        assembly {
            r := add(r, add(mload(0x80), mload(0xa0)))
        }
    }
}
