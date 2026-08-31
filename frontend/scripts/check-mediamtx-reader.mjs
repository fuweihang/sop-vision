import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const expectedSha256 =
  "a802f229b803c33713d4c69c4cc0d480108a5bf384947aeee4aaf04268bf85c1";
const readerUrl = new URL("../src/vendor/mediamtx/reader.js", import.meta.url);
const reader = await readFile(readerUrl);
const actualSha256 = createHash("sha256").update(reader).digest("hex");

if (actualSha256 !== expectedSha256) {
  throw new Error(
    `MediaMTX reader.js 校验失败：期望 ${expectedSha256}，实际 ${actualSha256}。`,
  );
}

console.log(`MediaMTX reader.js SHA-256 校验通过：${actualSha256}`);
