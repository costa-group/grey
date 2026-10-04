#!/bin/bash
# Builds, from scratch and at pinned commits, the tools of the gas evaluation of the semantic tests:
#   <build_root>/evmone-<ref8>/build/lib/libevmone.so   evmone at the pinned commit (and v0.18.0 for a cross-check)
#   <build_root>/solidity/build/test/tools/testrunner   testrunner of solidity's testExpectationExtraction branch
#                                                       with evaluation/scripts/testrunner_logs.patch (log/storage digests)
#   <build_root>/testrunner.orig                         the same testrunner without the patch
#   <build_root>/versions.txt                            the commits and compilers actually used
# Usage: build_testrunner.sh <build_root> [jobs]   (jobs: free cores given the load, minus 3; at least 4)
# The latest evmone (EVMC ABI 19) cannot be loaded by the EVMHost of the branch (EVMC ABI 12): keep these refs.
set -euo pipefail

BUILD_ROOT=$(realpath -m "${1:?build root}")
if [ -n "${2:-}" ]; then
    JOBS=$2
else
    JOBS=$(( $(nproc) - $(cut -d' ' -f1 /proc/loadavg | cut -d. -f1) - 3 ))
    [ "$JOBS" -lt 4 ] && JOBS=4  # the machine is often oversubscribed by other users
fi
PATCH_FILE=$(realpath "$(dirname "$0")/testrunner_logs.patch")
# evmone: the commit used in the earlier experiments of the group (2024-12-04) and the last release with ABI 12
EVMONE_REFS=(94582ffd91e11eeae2e0d08ad519681111c05d4e v0.18.0)
# solidity: head of testExpectationExtraction ("Output metadata for semantic tests", 2025-02-27)
SOLIDITY_COMMIT=cd4e61e869cdd012f74969755973d8a0f98b0629
mkdir -p "$BUILD_ROOT"
echo "build root $BUILD_ROOT, jobs $JOBS"

for ref in "${EVMONE_REFS[@]}"; do
    folder="$BUILD_ROOT/evmone-${ref:0:8}"
    if [ ! -f "$folder/build/lib/libevmone.so" ]; then
        [ -d "$folder" ] || git clone --quiet https://github.com/ipsilon/evmone "$folder"
        git -C "$folder" checkout --quiet "$ref"
        git -C "$folder" submodule update --init --recursive --quiet
        cmake -S "$folder" -B "$folder/build" -DCMAKE_BUILD_TYPE=Release -DEVMONE_TESTING=OFF > "$folder/cmake.log"
        cmake --build "$folder/build" --target evmone -j "$JOBS" > "$folder/build.log"
    fi
    echo "evmone $ref: $folder/build/lib/libevmone.so"
done

solidity="$BUILD_ROOT/solidity"
if [ ! -d "$solidity" ]; then
    git clone --quiet --branch testExpectationExtraction --single-branch https://github.com/argotorg/solidity "$solidity"
fi
git -C "$solidity" checkout --quiet -- test/tools/testrunner.cpp  # undo the patch of a previous build
git -C "$solidity" checkout --quiet "$SOLIDITY_COMMIT"
cmake -S "$solidity" -B "$solidity/build" -DCMAKE_BUILD_TYPE=Release -DTESTS=ON -DUSE_Z3=OFF -DUSE_CVC4=OFF \
    -DSTRICT_Z3_VERSION=OFF -DPEDANTIC=OFF > "$solidity/cmake.log"
cmake --build "$solidity/build" --target testrunner -j "$JOBS" > "$solidity/build.log" 2>&1
cp "$solidity/build/test/tools/testrunner" "$BUILD_ROOT/testrunner.orig"
git -C "$solidity" apply "$PATCH_FILE"
cmake --build "$solidity/build" --target testrunner -j "$JOBS" >> "$solidity/build.log" 2>&1
echo "testrunner: $solidity/build/test/tools/testrunner (patched), $BUILD_ROOT/testrunner.orig"

{
    echo "date $(date -u +%FT%TZ)"
    echo "solidity $(git -C "$solidity" rev-parse HEAD) + $(sha256sum "$PATCH_FILE" | cut -c1-16) testrunner_logs.patch"
    for ref in "${EVMONE_REFS[@]}"; do echo "evmone-${ref:0:8} $(git -C "$BUILD_ROOT/evmone-${ref:0:8}" rev-parse HEAD)"; done
    echo "compiler $(c++ --version | head -1)"
    echo "cmake $(cmake --version | head -1)"
} > "$BUILD_ROOT/versions.txt"
cat "$BUILD_ROOT/versions.txt"
