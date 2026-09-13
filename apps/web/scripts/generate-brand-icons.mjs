import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

// Mechanical exports of the approved artwork; never redraw the brand per size.
const webRoot = new URL("../", import.meta.url);
const source = fileURLToPath(new URL("public/brand/trafriend-mark.png", webRoot));
const sourceMetadata = await sharp(source).metadata();
if (sourceMetadata.width !== sourceMetadata.height) {
  throw new Error("The brand source must be square.");
}

function png(size) {
  return sharp(source).resize(size, size).ensureAlpha().png({ compressionLevel: 9 }).toBuffer();
}

for (const [destination, size] of [
  ["public/brand/trafriend-mark-96.png", 96],
  ["public/brand/trafriend-mark-192.png", 192],
  ["public/brand/trafriend-mark-512.png", 512],
  ["src/app/icon.png", 192],
  ["src/app/apple-icon.png", 180],
]) {
  await writeFile(new URL(destination, webRoot), await png(size));
}

// ICO's directory points to independent PNG frames for native browser sizes.
const sizes = [16, 32, 48, 64, 96];
const frames = await Promise.all(sizes.map(png));
const directory = Buffer.alloc(6 + sizes.length * 16);
directory.writeUInt16LE(1, 2);
directory.writeUInt16LE(sizes.length, 4);
let offset = directory.length;
for (let index = 0; index < sizes.length; index += 1) {
  const entry = 6 + index * 16;
  directory.writeUInt8(sizes[index], entry);
  directory.writeUInt8(sizes[index], entry + 1);
  directory.writeUInt16LE(1, entry + 4);
  directory.writeUInt16LE(32, entry + 6);
  directory.writeUInt32LE(frames[index].length, entry + 8);
  directory.writeUInt32LE(offset, entry + 12);
  offset += frames[index].length;
}
await writeFile(new URL("src/app/favicon.ico", webRoot), Buffer.concat([directory, ...frames]));
console.log("Exported header, PNG, Apple touch, and 16/32/48/64/96px favicon assets.");
