import { createHash, randomBytes } from "crypto";
import bs58 from "bs58";

export interface OneTimeReceiveCode {
  version: number;
  pubkeySpend: string; // hex string, 32B
  pubkeyView: string;  // hex string, 32B
  nonce: string;       // hex string, 16B
  checksum: string;    // hex string, 4B
}

// 工具：hex -> Buffer
function hexToBuf(hex: string): Buffer {
  return Buffer.from(hex.replace(/^0x/, ""), "hex");
}

// 工具：Buffer -> hex
function bufToHex(buf: Buffer): string {
  return "0x" + buf.toString("hex");
}

// 编码为 Base58 一次性接收码
export function encodeReceiveCode(spend: string, view: string): string {
  const version = Buffer.from([1]); // v1
  const pubkeySpend = hexToBuf(spend);
  const pubkeyView = hexToBuf(view);

  if (pubkeySpend.length !== 32) {
    throw new Error("pubkeySpend must be 32 bytes hex");
  }
  if (pubkeyView.length !== 32) {
    throw new Error("pubkeyView must be 32 bytes hex");
  }
  const nonce = randomBytes(16);

  const payload = Buffer.concat([version, pubkeySpend, pubkeyView, nonce]);

  // checksum: sha256(payload) 前4字节
  const checksum = createHash("sha256").update(payload).digest().subarray(0, 4);
  const full = Buffer.concat([payload, checksum]);

  return bs58.encode(full); // 返回 Base58 字符串
}

// 解码 Base58 一次性接收码
export function decodeReceiveCode(code: string): OneTimeReceiveCode {
  const buf = Buffer.from(bs58.decode(code));

  // 期望总长度：1 + 32 + 32 + 16 + 4 = 85 字节
  if (buf.length !== 85) {
    throw new Error("Invalid code length");
  }

  const version = buf[0];
  if (version !== 1) {
    throw new Error(`Unsupported version: ${version}`);
  }

  const pubkeySpendBuf = buf.subarray(1, 33);
  const pubkeyViewBuf = buf.subarray(33, 65);
  const nonceBuf = buf.subarray(65, 81);
  const checksumBuf = buf.subarray(81, 85);

  // 校验 checksum: sha256(payload)[0..4)
  const payload = buf.subarray(0, 81);
  const expected = createHash("sha256").update(payload).digest().subarray(0, 4);
  if (!checksumBuf.equals(expected)) {
    throw new Error("Invalid checksum");
  }

  return {
    version,
    pubkeySpend: bufToHex(pubkeySpendBuf),
    pubkeyView: bufToHex(pubkeyViewBuf),
    nonce: bufToHex(nonceBuf),
    checksum: bufToHex(checksumBuf),
  };
}
