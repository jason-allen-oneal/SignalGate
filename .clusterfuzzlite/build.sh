#!/bin/bash -eu

# ClusterFuzzLite build script.
# Builds Python fuzzers using OSS-Fuzz helper.

python3 -m pip install --no-cache-dir atheris==2.3.0

# Install the project (best-effort). If the repo is not installable as a package,
# fallback to using source imports via PYTHONPATH in fuzzers.
python3 -m pip install --no-cache-dir -e . || true

# Build fuzz targets.
for fuzzer in fuzz/fuzz_*.py; do
  compile_python_fuzzer "$fuzzer"
done
