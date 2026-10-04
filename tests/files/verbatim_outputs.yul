object "V" {
    code {
        let x := calldataload(0)
        let y := calldataload(32)
        // RETURNDATASIZE on top of x: two outputs (0, x)
        let a, b := verbatim_1i_2o(hex"3d", x)
        // SUB of the two inputs: the first argument is on top
        let d := verbatim_2i_1o(hex"03", y, b)
        verbatim_0i_0o(hex"5b")
        mstore(0, d)
        mstore(32, a)
        mstore(64, b)
        return(0, 96)
    }
}
