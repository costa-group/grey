//Solc command line: ../AFLs/new-solidity/build/solc/solc generated_programs/program_2024-12-17_17:35:8_27.sol --asm --yul-optimizations oEDVnxapifleursthCOScIMjLFUg --optimize-runs 6 --optimize-yul --model-checker-ext-calls untrusted --via-ir

contract contract0 {
  struct struct1 {
    bool var2;
  }

  int16 internal var3;

  function func4(int16 var5) internal returns (mapping(int16 => int16[]) storage mapping6, struct1 memory struct_instance10) {
    mapping6 = mapping6;
    struct_instance10 = struct_instance10;
    (bool(false) ? var3 : (var3));
  }

  function func11(mapping(int16 => int16)[] storage array12) internal view returns (int16 var16) {
    struct1 memory struct_instance17;
    struct_instance17 = struct_instance17;
    if (struct_instance17.var2 && (false)) {} else {
      (var3) % (var3);
    }
  }
}

contract contract18 {
  error error19();

  error error20(int16 var21);

  struct struct22 {
    int256[][4] array23;
    contract0.struct1 struct_instance26;
  }

  bool internal var27;

  constructor(contract18.struct22[2] memory array28) {
    contract18.struct22 memory struct_instance38;
    struct_instance38 = struct_instance38;
    contract0.struct1 memory struct_instance39;
    struct_instance39 = struct_instance39;
    true ? struct_instance39 : (struct_instance38.struct_instance26);
  }

  function func30(mapping(string => struct22) storage mapping31) internal returns (contract0 contract_instance34, contract0.struct1 memory struct_instance35) {
    struct_instance35 = struct_instance35;
    (this.func36());
  }

  function func36() external returns (struct22 memory struct_instance37) {
    struct_instance37 = struct_instance37;
    contract0.struct1 memory struct_instance40;
    struct_instance40 = struct_instance40;
    contract18.struct22 memory struct_instance41;
    struct_instance41 = struct_instance41;
    for (; struct_instance40.var2 || var27; var27 ? (struct_instance40) : (struct_instance41.struct_instance26)) {
      var27 ? true : struct_instance41.struct_instance26.var2;
    }
    return (this.func36());
  }
}
