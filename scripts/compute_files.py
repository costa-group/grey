
examples/solc examples/complex/complex.yul --optimize --strict-assembly --yul-cfg-json --pretty-json &> complex.cfg

mv complex.cfg examples/complex/


examples/solc examples/complex/complex.yul --optimize --strict-assembly --pretty-json --asm-json &> complex-asm-solc.json

mv comples-asm-solc.json examples/complex/

python3 src/grey_main.py -s examples/complex/complex.cfg -g -v -if yul-cfg -solc examples/solc -o complex

cp complex/*/*_asm.json expamples/complex/.
