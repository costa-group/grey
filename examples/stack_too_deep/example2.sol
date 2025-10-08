function sum(
    uint x01, uint x02, uint x03, uint x04,
    uint x05, uint x06, uint x07, uint x08,
    uint x09, uint x10, uint x11, uint x12,
    uint x13, uint x14, uint x15, uint x16,
    uint x17, uint x18
) returns (uint)
{
    return
        x01 + x02 + x03 + x04 +
        x05 + x06 + x07 + x08 +
        x09 + x10 + x11 + x12 +
        x13 + x14 + x15 + x16 +
        x17 + x18;
}

function arg(uint i) returns (uint) {
    return i * i + i * i;
}

function f(
    uint a01, uint a02, uint a03, uint a04,
    uint a05, uint a06, uint a07, uint a08,
    uint a09, uint a10, uint a11, uint a12,
    uint a13, uint a14, uint a15, uint a16,
    uint a17, uint a18
) returns (uint) {
    uint u01 = arg(a01); uint u02 = arg(a02); uint u03 = arg(a03); uint u04 = arg(a04);
    uint u05 = arg(a05); uint u06 = arg(a06); uint u07 = arg(a07); uint u08 = arg(a08);
    uint u09 = arg(a09); uint u10 = arg(a10); uint u11 = arg(a11); uint u12 = arg(a12);
    uint u13 = arg(a13); uint u14 = arg(a14); uint u15 = arg(a15); uint u16 = arg(a16);
    uint u17 = arg(a17); uint u18 = arg(a18);
    return sum(
        u18, u17,
        u16, u15, u14, u13,
        u12, u11, u10, u09,
        u08, u07, u06, u05,
        u04, u03, u02, u01
    );
}

contract C {
    function run() public {
        f(
             1,  2,  3,  4,
             5,  6,  7,  8,
             9, 10, 11, 12,
            13, 14, 15, 16,
            17, 18
        );
    }
}
