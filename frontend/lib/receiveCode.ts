// Browser-compatible receive code utils (no Node 'crypto')
import bs58 from "bs58";
import { keccak256, toUtf8Bytes, getAddress } from "ethers";

export interface OneTimeReceiveCode {
  version: number;
  pubkeySpend: string; // 0x-prefixed hex, 32B
  pubkeyView: string;  // 0x-prefixed hex, 32B
  nonce: string;       // 0x-prefixed hex, 16B
  checksum: string;    // 0x-prefixed hex, 4B
}

function hexToBuf(hex: string): Uint8Array {
  const clean = hex.replace(/^0x/, "");
  if (clean.length % 2 !== 0) throw new Error("invalid hex length");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function bufToHex(buf: Uint8Array): string {
  return (
    "0x" + Array.from(buf).map((b) => b.toString(16).padStart(2, "0")).join("")
  );
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return new Uint8Array(digest);
}

export function generateNonce16(): Uint8Array {
  const nonce = new Uint8Array(16);
  crypto.getRandomValues(nonce);
  return nonce;
}

export function derivePubkeysFromAddress(address: string): { spend: string; view: string } {
  const norm = getAddress(address); // checksum format
  const spend = keccak256(toUtf8Bytes(norm.toLowerCase() + ":spend")); // 32B hex
  const view = keccak256(toUtf8Bytes(norm.toLowerCase() + ":view"));   // 32B hex
  return { spend, view };
}

export async function encodeReceiveCode(
  spend: string,
  view: string,
  nonceOverride?: Uint8Array
): Promise<string> {
  const version = new Uint8Array([1]);
  const pubkeySpend = hexToBuf(spend);
  const pubkeyView = hexToBuf(view);
  if (pubkeySpend.length !== 32) throw new Error("pubkeySpend must be 32 bytes hex");
  if (pubkeyView.length !== 32) throw new Error("pubkeyView must be 32 bytes hex");
  const nonce = nonceOverride ?? generateNonce16();

  const payload = new Uint8Array(version.length + pubkeySpend.length + pubkeyView.length + nonce.length);
  payload.set(version, 0);
  payload.set(pubkeySpend, 1);
  payload.set(pubkeyView, 33);
  payload.set(nonce, 65);

  const digest = await sha256(payload);
  const checksum = digest.slice(0, 4);

  const full = new Uint8Array(payload.length + checksum.length);
  full.set(payload, 0);
  full.set(checksum, payload.length);

  return bs58.encode(full);
}

export async function decodeReceiveCode(code: string): Promise<OneTimeReceiveCode> {
  const buf = bs58.decode(code);
  if (buf.length !== 85) throw new Error("Invalid code length");
  const version = buf[0];
  if (version !== 1) throw new Error(`Unsupported version: ${version}`);

  const payload = buf.slice(0, 81);
  const checksum = buf.slice(81, 85);
  const expected = (await sha256(payload)).slice(0, 4);
  if (checksum.some((b, i) => b !== expected[i])) throw new Error("Invalid checksum");

  return {
    version,
    pubkeySpend: bufToHex(buf.slice(1, 33)),
    pubkeyView: bufToHex(buf.slice(33, 65)),
    nonce: bufToHex(buf.slice(65, 81)),
    checksum: bufToHex(checksum)
  };
}
