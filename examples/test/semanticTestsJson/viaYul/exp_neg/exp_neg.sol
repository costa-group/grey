contract C {
    function f(int x, uint y) public returns (int) {
        return x**y;
    }
}
// ----
// f(int256,uint256): 0, 0 -> 1
// f(int256,uint256): 0, 1 -> 0x00
// f(int256,uint256): 0, 2 -> 0x00
// f(int256,uint256): 1, 0 -> 1
// f(int256,uint256): 1, 1 -> 1
// f(int256,uint256): 1, 2 -> 1
// f(int256,uint256): 2, 0 -> 1
// f(int256,uint256): 2, 1 -> 2
// f(int256,uint256): 2, 2 -> 4
// f(int256,uint256): 7, 63 -> 174251498233690814305510551794710260107945042018748343
// f(int256,uint256): 128, 2 -> 0x4000
// f(int256,uint256): -1, 0 -> 1
// f(int256,uint256): -1, 1 -> -1
// f(int256,uint256): -1, 2 -> 1
// f(int256,uint256): -2, 0 -> 1
// f(int256,uint256): -2, 1 -> -2
// f(int256,uint256): -2, 2 -> 4
// f(int256,uint256): -7, 63 -> -174251498233690814305510551794710260107945042018748343
// f(int256,uint256): -128, 2 -> 0x4000
// f(int256,uint256): -1, 115792089237316195423570985008687907853269984665640564039457584007913129639935 -> -1
// f(int256,uint256): -2, 255 -> -57896044618658097711785492504343953926634992332820282019728792003956564819968
// f(int256,uint256): -8, 85 -> -57896044618658097711785492504343953926634992332820282019728792003956564819968
// f(int256,uint256): -131072, 15 -> -57896044618658097711785492504343953926634992332820282019728792003956564819968
// f(int256,uint256): -32, 51 -> -57896044618658097711785492504343953926634992332820282019728792003956564819968
// f(int256,uint256): -57896044618658097711785492504343953926634992332820282019728792003956564819968, 1 -> -57896044618658097711785492504343953926634992332820282019728792003956564819968