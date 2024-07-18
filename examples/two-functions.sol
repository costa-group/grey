pragma solidity ^0.8.24;

contract A {

  uint a;


  function f(uint x) public returns (uint y) {
    assembly{
      let z := 2*x
    y := a+z+1
    }
  }

  function g() public {
    f(5);
  }
  
  
}
