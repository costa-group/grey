"""
Methods for parsing the options to execute grey
"""
import argparse
import global_params.constants as constants


def generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grey Project")

    input_options = parser.add_argument_group("Input Options")

    input_options.add_argument("-s", "--source", type=str, help="Local source file name. By default, it assumes the"
                                                                "Yul CFG JSON format", required=True)
    input_options.add_argument("-if", "--input-format", dest="input_format", type=str,
                               help="Sets the input format: a sol file, the standard-json input or a Yul CFG JSON."
                                    "By default, it assumes the Yul CFG.", choices=["sol", "standard-json", "yul-cfg"],
                               default="yul-cfg")
    input_options.add_argument("-c", "--contract", type=str, dest="contract",
                               help="Specify which contract must be synthesized. "
                                    "If no contract is specified, all contracts synthesized.")
    input_options.add_argument("-solc", "--solc", type=str, dest="solc_executable", default="solc",
                               help="Solc executable. By default, it assumes it can invoke 'solc'")

    output_options = parser.add_argument_group("Output Options")
    output_options.add_argument("-o", "--folder", type=str, help="Dir to store the results.", default="/tmp/grey/")
    output_options.add_argument("-v", "--visualize", action="store_true", dest="visualize",
                                help="Generates a dot file for each object in the JSON, "
                                     "showcasing the results from the liveness analysis")
    output_options.add_argument("-json-solc", "--json-solc", action="store_true", dest="json_solc",
                                help="Stores the result in combined-json format")
    output_options.add_argument("-auxdata", "--auxdata", action="store_true", dest="auxdata", help="Enabled the generation of auxdata as part of the evm code")

    synthesis_options = parser.add_argument_group("Synthesis Options")
    synthesis_options.add_argument("-g", "--greedy", action="store_true", help="Enables the greedy algorithm")
    synthesis_options.add_argument("-bt", "--builtin-ops", action="store_true", dest="builtin",
                                   help="Keeps the original builtin opcodes")
    synthesis_options.add_argument("-j", "--junk", action="store_false", help="Disables garbage generation")
    synthesis_options.add_argument("-d", "--depth", type=int, default=16, dest="depth",
                                   help="Set the maximum depth to access the stack (TESTING STACK-TOO-DEEP ONLY)")
    return parser


def parse_args() -> argparse.Namespace:
    parser = generate_parser()
    parsed_args = parser.parse_args()
    if parsed_args.depth <= 0:
        raise ValueError(f"Depth argument must be > 0: {parsed_args.depth}")
    else:
        constants.MAX_STACK_DEPTH = parsed_args.depth
    return parsed_args
