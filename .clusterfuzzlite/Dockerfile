FROM gcr.io/oss-fuzz-base/base-builder-python:v1
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install numpy==2.0.0
COPY . $SRC/SignalGate
WORKDIR $SRC/SignalGate
COPY .clusterfuzzlite/build.sh $SRC/build.sh
