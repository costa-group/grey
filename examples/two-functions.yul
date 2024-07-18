{
  function f(x) -> y {
     let z := mul(2,x)   
     let a := sload(0)
     if gt(a,x) {
        sstore(x,x)
     }{
        sstore(z,x)
     }
     y := add(a,add(z,1))
  } 

 pop(f(calldataload(4)))

}
