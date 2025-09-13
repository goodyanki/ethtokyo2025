export type Calldata = {
  a: [string, string];
  b: [[string, string], [string, string]];
  c: [string, string];
  input: string[];
};

// 只在浏览器端调用（被 client 组件使用）。
export async function genProof(
  input: Record<string, any>,
  wasmPath = "/zk/income_threshold.wasm",
  zkeyPath = "/zk/income_threshold_final.zkey"
) {
  const snarkjs = await import("snarkjs");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, wasmPath, zkeyPath);
  return { proof, publicSignals } as { proof: any; publicSignals: string[] };
}

export async function toSolidityCalldata(proof: any, publicSignals: string[]): Promise<Calldata> {
  const snarkjs = await import("snarkjs");
  const calldata = await snarkjs.groth16.exportSolidityCallData(proof, publicSignals);
  const parsed = JSON.parse(`[${calldata}]`);
  const a = parsed[0] as [string, string];
  const b = parsed[1] as [[string, string], [string, string]];
  const c = parsed[2] as [string, string];
  const input = parsed[3] as string[];
  return { a, b, c, input };
}

// 可选：在前端做本地验证（若你复制了 verification_key.json 到 /zk/）
export async function verifyOffchain(
  proof: any,
  publicSignals: string[],
  vkJsonUrl = "/zk/verification_key.json"
): Promise<boolean> {
  const snarkjs = await import("snarkjs");
  const vk = await fetch(vkJsonUrl).then((r) => r.json());
  return snarkjs.groth16.verify(vk, publicSignals, proof);
}
