// frontend/lib/proof.ts
// 生成 Semaphore 证明并打包给 Solidity
// 依赖：snarkjs、circomlibjs、ethers（只为 keccak/地址工具，可替换）

import { groth16 } from "snarkjs";
import { buildPoseidon } from "circomlibjs";
import { keccak256, getAddress, hexlify, getBytes } from "ethers";

// BN254 素数（Fr 模数）
const P = BigInt("21888242871839275222246405745257275088548364400416034343698204186575808495617");

export type MerklePath = {
  elements: string[]; // 十六进制字符串（0x...），每层一个 Poseidon 节点
  indices: number[];  // 每层 0/1
};

export type Identity = {
  nullifier: bigint;  // Fr
  trapdoor: bigint;   // Fr
  commitment: string; // 0x.. hex (Poseidon(nullifier, trapdoor))
};

export type PublicSignals = {
  merkleRoot: string;
  nullifierHash: string;
  externalNullifier: string;
  signalHash: string;
};

export type PackedProof = [string, string, string, string, string, string, string, string];

export async function poseidon2(a: bigint, b: bigint): Promise<bigint> {
  const poseidon = await buildPoseidon();
  const r = poseidon.F.toObject(poseidon([a, b]));
  return BigInt(r.toString());
}

export function toFr(x: bigint | string | Uint8Array): bigint {
  let n: bigint;
  if (typeof x === "bigint") n = x;
  else if (typeof x === "string") {
    const h = x.startsWith("0x") ? x.slice(2) : x;
    n = BigInt("0x" + (h.length ? h : "0"));
  } else {
    n = BigInt("0x" + Buffer.from(x).toString("hex"));
  }
  n %= P;
  if (n < 0n) n += P;
  return n;
}

export function randFr(): bigint {
  const buf = new Uint8Array(32);
  crypto.getRandomValues(buf);
  return toFr(buf);
}

export async function makeIdentity(): Promise<Identity> {
  const nullifier = randFr();
  const trapdoor  = randFr();
  const c = await poseidon2(nullifier, trapdoor);
  return { nullifier, trapdoor, commitment: "0x" + c.toString(16) };
}

// 简易 Poseidon Merkle 树（完全二叉），深度 LEVELS，叶子长度须 ≤ 2^LEVELS
export async function buildMerkle(leavesHex: string[], levels: number) {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;

  const toB = (h: string) => BigInt(h);
  const hash2 = (x: bigint, y: bigint) => BigInt(F.toObject(poseidon([x, y])).toString());

  // 填充到 2^levels
  const size = 1 << levels;
  const leaves: bigint[] = Array(size).fill(0n);
  for (let i = 0; i < leavesHex.length; i++) leaves[i] = toB(leavesHex[i]);

  const layers: bigint[][] = [leaves];
  for (let d = 0; d < levels; d++) {
    const prev = layers[d];
    const next: bigint[] = [];
    for (let i = 0; i < prev.length; i += 2) {
      next.push(hash2(prev[i], prev[i + 1]));
    }
    layers.push(next);
  }
  const root = layers[levels][0];

  function getPath(leafIndex: number) {
    const elements: string[] = [];
    const indices: number[] = [];
    let idx = leafIndex;
    for (let d = 0; d < levels; d++) {
      const sib = idx ^ 1;
      elements.push("0x" + layers[d][sib].toString(16));
      indices.push(idx & 1);
      idx = Math.floor(idx / 2);
    }
    return { elements, indices };
  }

  return { root: "0x" + root.toString(16), getPath };
}

// keccak256(hex/bytes) → Fr
export function keccakToFr(inputHex: string | Uint8Array): bigint {
  const hex = typeof inputHex === "string" ? inputHex : hexlify(inputHex);
  const h = keccak256(hex);
  return toFr(h);
}

// 生成 publicSignals
export async function makePublicSignals(params: {
  merkleRoot: string;
  identityNullifier: bigint;
  escrowIdHex32: string; // 0x..32B
  toAddress: string;     // 0x..20B
}): Promise<PublicSignals> {
  const merkleRoot = params.merkleRoot;
  const externalNullifier = "0x" + keccakToFr(params.escrowIdHex32).toString(16);
  // abi.encodePacked(escrowIdHex32 || toAddress)
  const escrowBytes = getBytes(params.escrowIdHex32);
  const addrBytes = getBytes(getAddress(params.toAddress));
  const packed = new Uint8Array(escrowBytes.length + addrBytes.length);
  packed.set(escrowBytes, 0);
  packed.set(addrBytes, escrowBytes.length);
  const signalHash = "0x" + keccakToFr(packed).toString(16);

  const nullifierPoseidon = await poseidon2(
    params.identityNullifier,
    BigInt(externalNullifier)
  );

  return {
    merkleRoot,
    nullifierHash: "0x" + nullifierPoseidon.toString(16),
    externalNullifier,
    signalHash,
  };
}

// 将 snarkjs 的 proof 打包成 solidity 期望的 uint256[8]
export function packGroth16Proof(proof: any): PackedProof {
  // 注意：snarkjs 返回的 b 是 [ [b00, b01], [b10, b11] ]
  const a = proof.pi_a;         // [ax, ay, 1]
  const b = proof.pi_b;         // [[bx1, bx0], [by1, by0], [1,1]]
  const c = proof.pi_c;         // [cx, cy, 1]
  return [
    a[0], a[1],
    b[0][1], b[0][0],
    b[1][1], b[1][0],
    c[0], c[1],
  ] as PackedProof;
}

// 生成证明（浏览器或 Node），需要 .wasm / .zkey
export async function generateSemaphoreProof(input: {
  identityNullifier: bigint;
  identityTrapdoor: bigint;
  merklePath: MerklePath;
  merkleRoot: string;
  escrowIdHex32: string;
  toAddress: string;
  wasmPath: string;   // e.g. /semaphore_js/semaphore.wasm
  zkeyPath: string;   // e.g. /semaphore.zkey
}) {
  const pub = await makePublicSignals({
    merkleRoot: input.merkleRoot,
    identityNullifier: input.identityNullifier,
    escrowIdHex32: input.escrowIdHex32,
    toAddress: input.toAddress,
  });

  const witnessInput = {
    identityNullifier: input.identityNullifier.toString(),
    identityTrapdoor:  input.identityTrapdoor.toString(),
    pathElements:      input.merklePath.elements.map(toFr).map(String),
    pathIndex:         input.merklePath.indices.map(String),

    // public signals
    merkleRoot:        toFr(pub.merkleRoot).toString(),
    nullifierHash:     toFr(pub.nullifierHash).toString(),
    externalNullifier: toFr(pub.externalNullifier).toString(),
    signalHash:        toFr(pub.signalHash).toString(),
  };

  const { proof, publicSignals } = await groth16.fullProve(
    witnessInput,
    input.wasmPath,
    input.zkeyPath
  );

  // 可选：校验返回的 publicSignals 顺序与期望一致
  // [merkleRoot, nullifierHash, externalNullifier, signalHash]
  const [mr, nh, en, sh] = publicSignals.map((x: string) => "0x" + BigInt(x).toString(16));
  if (
    toFr(mr) !== toFr(pub.merkleRoot) ||
    toFr(nh) !== toFr(pub.nullifierHash) ||
    toFr(en) !== toFr(pub.externalNullifier) ||
    toFr(sh) !== toFr(pub.signalHash)
  ) {
    throw new Error("publicSignals mismatch");
  }

  return {
    proofPacked: packGroth16Proof(proof),
    publicSignals: pub, // 给合约的 4 个
  };
}
