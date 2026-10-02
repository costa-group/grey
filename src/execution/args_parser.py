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
    input_options.add_argument("--solc-cfg-fallback", type=str, dest="solc_cfg_fallback", default=None,
                               help="Solc executable used to generate the Yul CFG when the one given with -solc fails "
                                    "with an internal error. The importer still uses the one given with -solc")
    
    input_options.add_argument("-solc-layouts", "--solc-layouts", action="store_true", dest="solc_layouts",
                               help="Solc executable. By default, it assumes it can invoke 'solc'")

    output_options = parser.add_argument_group("Output Options")
    output_options.add_argument("-o", "--folder", type=str, help="Dir to store the results.", default="/tmp/grey/")
    output_options.add_argument("-v", "--visualize", action="store_true", dest="visualize",
                                help="Generates a dot file for each object in the JSON, "
                                     "showcasing the results from the liveness analysis")
    output_options.add_argument("-sfs", "--sfs", action="store_true", dest="sfs", help="Stores the SFS information "
                                                                                     "according to the format used by GASOL. "
                                                                                     "It uses information from the greedy algorithm")
    output_options.add_argument("-json-solc", "--json-solc", action="store_true", dest="json_solc",
                                help="Stores the result in combined-json format")
    output_options.add_argument("-auxdata", "--auxdata", action="store_true", dest="auxdata", help="Enabled the generation of auxdata as part of the evm code")
    output_options.add_argument("--debug", action="store_true", dest="debug",
                                help="Performs the safety checks (greedy and memory slots validation) and stores "
                                     "the debug dumps in the output folder. Disabled by default, "
                                     "as the checks distort the measured times")

    synthesis_options = parser.add_argument_group("Synthesis Options")
    synthesis_options.add_argument("-g", "--greedy", action="store_true", help="Enables the greedy algorithm")
    synthesis_options.add_argument("-bt", "--builtin-ops", action="store_true", dest="builtin",
                                   help="Keeps the original builtin opcodes")
    synthesis_options.add_argument("-j", "--junk", action="store_false", help="Disables garbage generation")
    synthesis_options.add_argument("-d", "--depth", type=int, default=16, dest="depth",
                                   help="Set the maximum depth to access the stack (TESTING STACK-TOO-DEEP ONLY)")
    synthesis_options.add_argument("--no-inline", action="store_false",
                                   help="Disables the default inlining", dest="inline")
    synthesis_options.add_argument("--junk-strategy", choices=["current", "simulated"], default="current",
                                   dest="junk_strategy",
                                   help="Experimental: how junk is placed in the output stacks. 'simulated' keeps junk only "
                                        "at the bottom, choosing the boundary by simulating the block")
    synthesis_options.add_argument("--new-vars-order", choices=["h1", "tiers"], default="h1", dest="new_vars_order",
                                   help="Experimental: order of the new variables in the output stacks. 'tiers' places "
                                        "first the values the successor consumes first")
    synthesis_options.add_argument("--split-critical-edges", action="store_true", dest="split_critical_edges",
                                   help="Experimental: splits the critical edges of the CFG with empty blocks, so that "
                                        "the predecessors of a join always have a single successor")
    synthesis_options.add_argument("--no-edge-dominance", action="store_false", dest="edge_dominance",
                                   help="Experimental: with --split-critical-edges, do not preserve the stack of a "
                                        "conditional block along the then-branch of an if without else")
    synthesis_options.add_argument("--hoist-return-labels", nargs="?", const="shared", default=None,
                                   choices=["shared", "branch", "max"], dest="hoist_return_labels",
                                   help="Experimental: pushes the return label of each call earlier, in a block from "
                                        "which every path reaches the call: the lowest one above the blocks that "
                                        "have equivalent copies ('shared', the default), the nearest branch point "
                                        "('branch') or the highest one ('max')")
    synthesis_options.add_argument("--solc-dedup", choices=["auto", "on", "off"], default="auto", dest="solc_dedup",
                                   help="Whether solc's block deduplicator runs on the generated assembly, which the "
                                        "merging of equivalent blocks takes into account. 'auto' (the default) "
                                        "detects it by importing a small assembly with the given solc")
    synthesis_options.add_argument("--no-merge-equivalent", action="store_false", dest="merge_equivalent",
                                   help="Disables merging the equivalent blocks in the acyclic tails of the CFG")
    synthesis_options.add_argument("--constants", action="store_false",
                                   help="Disables constant propagation", dest="constants")
    synthesis_options.add_argument("--thread-empty-blocks", action="store_true", dest="thread_empty_blocks",
                                   help="Experimental: skips at emission every block whose code is only its jump "
                                        "(jump threading), not only grey's edge blocks")
    synthesis_options.add_argument("--reinline-after-merge", action="store_true", dest="reinline_after_merge",
                                   help="Experimental: inlines again, after merging the equivalent blocks, the "
                                        "functions that are now called from a single place")
    synthesis_options.add_argument("--combine-functions", action="store_true", dest="combine_functions",
                                   help="Experimental: combines the functions with equivalent bodies before inlining "
                                        "(as solc's EquivalentFunctionCombiner does before its inliner)")
    synthesis_options.add_argument("--prune-unused-arguments", action="store_true", dest="prune_unused_arguments",
                                   help="Experimental: removes the arguments a function never uses, from the function "
                                        "and its calls, before inlining (as solc's UnusedFunctionParameterPruner)")
    synthesis_options.add_argument("--cse", action="store_true", dest="cse",
                                   help="Applies on the CFG the simplifications that solc's optimizer does not apply "
                                        "to grey's code (e.g. return(literal, 0) -> stop())")
    synthesis_options.add_argument("--no-push-dup", action="store_false", dest="push_dup",
                                   help="Disables replacing the PUSHes of values that are already in the stack by "
                                        "DUPs in the code generated by the greedy")
    synthesis_options.add_argument("--no-fallthrough", action="store_false", dest="fallthrough",
                                   help="Keeps the unconditional jumps to the block placed right after the jump "
                                        "(PUSH [tag] JUMP to the next instruction) instead of falling through")
    return parser


def parse_args() -> argparse.Namespace:
    parser = generate_parser()
    parsed_args = parser.parse_args()
    if parsed_args.depth <= 0:
        raise ValueError(f"Depth argument must be > 0: {parsed_args.depth}")
    else:
        constants.MAX_STACK_DEPTH = parsed_args.depth
    constants.DEBUG = parsed_args.debug
    constants.THREAD_EMPTY_BLOCKS = getattr(parsed_args, "thread_empty_blocks", False)
    constants.PUSH_DUP = parsed_args.push_dup
    constants.SOLC_CFG_FALLBACK = parsed_args.solc_cfg_fallback
    constants.FALLTHROUGH = parsed_args.fallthrough
    return parsed_args
