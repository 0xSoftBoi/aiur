# Host build of the FTU decision logic and packet format.  No Arduino, no
# PlatformIO: g++ and python3 only.
#
#   make            generate vectors from the Python reference, build, run
#   make sanitize   the same under AddressSanitizer + UBSan
#   make clean
#
# -ffast-math must never be added: the parity check depends on IEEE-754
# comparison semantics (NaN compares false), as does the firmware.

CXX      ?= g++
PYTHON   ?= python3
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Werror -Wshadow -Wconversion -Wdouble-promotion
REPO     := ../../..
SRC      := ../src/geofence.cpp ../src/protocol.cpp ftu_host_test.cpp
HDR      := ../src/geofence.hpp ../src/protocol.hpp
BUILD    := build

.PHONY: all test sanitize clean vectors
all: test

vectors: $(BUILD)/vectors.csv

# Regenerated whenever the reference or the generator changes.
$(BUILD)/vectors.csv: $(REPO)/tools/ftu_vectors.py $(REPO)/aiur/strato/guidance.py $(REPO)/aiur/strato/atmosphere.py
	@mkdir -p $(BUILD)
	$(PYTHON) $(REPO)/tools/ftu_vectors.py --out $@

$(BUILD)/ftu_host_test: $(SRC) $(HDR)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

$(BUILD)/ftu_host_test_san: $(SRC) $(HDR)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -o $@ $(SRC)

test: $(BUILD)/ftu_host_test $(BUILD)/vectors.csv
	$(BUILD)/ftu_host_test $(BUILD)/vectors.csv

sanitize: $(BUILD)/ftu_host_test_san $(BUILD)/vectors.csv
	$(BUILD)/ftu_host_test_san $(BUILD)/vectors.csv

clean:
	rm -rf $(BUILD)
