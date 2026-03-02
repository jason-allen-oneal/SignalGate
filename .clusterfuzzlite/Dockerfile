FROM gcr.io/oss-fuzz-base/base-builder-python:v1

# Install dependencies
RUN pip3 install --upgrade pip && pip3 install atheris

# Copy source
COPY . $SRC/signalgate-router
WORKDIR $SRC/signalgate-router

# Copy fuzzers
COPY .clusterfuzzlite/fuzz_sanitize.py $SRC/

# Build script
RUN echo "python3 -m atheris_no_libfuzzer \$SRC/fuzz_sanitize.py" > $OUT/fuzz_sanitize && chmod +x $OUT/fuzz_sanitize
