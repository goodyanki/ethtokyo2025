SHELL := /bin/bash

# Circuit names and paths
CIRCUIT := income_threshold
SRC := src/$(CIRCUIT).circom
BUILD := build
INPUT := inputs/input.json

# Artifacts
R1CS := $(BUILD)/$(CIRCUIT).r1cs
WASM := $(BUILD)/$(CIRCUIT)_js/$(CIRCUIT).wasm
SYM := $(BUILD)/$(CIRCUIT).sym
WITNESS := $(BUILD)/witness.wtns

# Powers of Tau (Phase 1)
TAU_POW := 12
PTAU0 := $(BUILD)/pot$(TAU_POW)_0000.ptau
PTAU1 := $(BUILD)/pot$(TAU_POW)_0001.ptau
PTAUF := $(BUILD)/pot$(TAU_POW)_final.ptau

# Groth16 keys
ZKEY0 := $(BUILD)/$(CIRCUIT)_0000.zkey
ZKEY := $(BUILD)/$(CIRCUIT)_final.zkey
VK := $(BUILD)/verification_key.json

# Proof
PROOF := $(BUILD)/proof.json
PUBLIC := $(BUILD)/public.json

# Verifier output (to contracts src)
VERIFIER := ../contracts/src/IncomeThresholdVerifier.sol

.PHONY: all compile witness ptau setup export-vk prove verify verifier clean

all: compile ptau setup export-vk witness prove verify verifier ## Full pipeline

compile: $(R1CS) $(WASM) $(SYM) ## Compile circom to r1cs/wasm/sym

$(R1CS) $(WASM) $(SYM): $(SRC)
	@mkdir -p $(BUILD)
	circom $(SRC) --r1cs --wasm --sym -l . -o $(BUILD)

witness: $(WITNESS) ## Generate witness from input.json

$(WITNESS): $(WASM) $(INPUT)
	node $(BUILD)/$(CIRCUIT)_js/generate_witness.js $(WASM) $(INPUT) $(WITNESS)

ptau: $(PTAUF) ## Phase1 Powers of Tau artifacts

$(PTAU0):
	snarkjs powersoftau new bn128 $(TAU_POW) $(PTAU0) -v

$(PTAU1): $(PTAU0)
	snarkjs powersoftau contribute $(PTAU0) $(PTAU1) --name="contrib1" -v

$(PTAUF): $(PTAU1)
	snarkjs powersoftau prepare phase2 $(PTAU1) $(PTAUF)

setup: $(ZKEY) ## Groth16 setup + contribution

$(ZKEY0): $(R1CS) $(PTAUF)
	snarkjs groth16 setup $(R1CS) $(PTAUF) $(ZKEY0)

$(ZKEY): $(ZKEY0)
	snarkjs zkey contribute $(ZKEY0) $(ZKEY) --name="key1" -v

export-vk: $(VK) ## Export verification key JSON

$(VK): $(ZKEY)
	snarkjs zkey export verificationkey $(ZKEY) $(VK)

prove: $(PROOF) $(PUBLIC) ## Create proof/public signals

$(PROOF) $(PUBLIC): $(ZKEY) $(WITNESS)
	snarkjs groth16 prove $(ZKEY) $(WITNESS) $(PROOF) $(PUBLIC)

verify: $(VK) $(PROOF) $(PUBLIC) ## Verify proof locally
	snarkjs groth16 verify $(VK) $(PUBLIC) $(PROOF)

verifier: $(VERIFIER) ## Export Solidity verifier contract

$(VERIFIER): $(ZKEY)
	@mkdir -p $(dir $(VERIFIER))
	snarkjs zkey export solidityverifier $(ZKEY) $(VERIFIER)

clean:
	rm -rf $(BUILD)
	rm -f $(VERIFIER)
