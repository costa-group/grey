// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
contract MultipleReturnsAssembly {
    function g(uint256 p, uint256 q) external pure returns (uint256 x, uint256 y, uint256 z, uint256 w) {
        assembly {
            function pair(u, v) -> a, b {
                a := add(mul(u, 3), calldataload(v))
                b := xor(sub(v, u), calldataload(u))
                if gt(a, b) { a := add(a, keccak256(0, 64)) }
            }
            x, y := pair(p, q)
            z, w := pair(add(q, 1), p)
        }
    }
}
