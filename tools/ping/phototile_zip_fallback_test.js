// =====================================================================
// makeZip stored-fallback 實測（2026-08-03・Codex 二輪 B2 的驗證）
//
// 為什麼要這支：0803 的 makeZip 重寫在 fallback（deflate 不划算 → method=0 stored）
// 忘了清 comp ⇒ header 寫 stored、內容塞 deflate bytes＝壞 ZIP。黃金五輪沒炸是因為
// 現有 entries 全部可壓縮、這條路**從未被走到**——「沒走到的路＝沒驗過的路」。
// 本測強迫走到：高熵（crypto 亂數）entry 的 deflate 必然變大 ⇒ 必走 stored。
//
// 驗四件（每件都是「壞 ZIP 就必紅」的檢查）：
//   ① local header 的 method／clen／rlen 與實際 payload 一致
//   ② stored entry 的 payload 逐位元 == 原始輸入
//   ③ deflated entry 用 zlib inflateRaw 解回來 == 原始輸入
//   ④ 每個 entry 的 CRC32 與 header 宣告一致（用 node zlib.crc32）
// 跑法：node tools/ping/phototile_zip_fallback_test.js（需 Node 18+：有 CompressionStream/Blob）
// =====================================================================
'use strict';
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const assert = require('assert');

// ---- 載入 engine.js（UMD：node require 即可；protocol_test 同款做法）----
const Engine = require(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'engine.js'));
assert(Engine && Engine._internals && Engine._internals.makeZip, 'makeZip 沒有曝露在 _internals');

// ---- CRC32（獨立實作對拍，不用受測碼自己的表）----
const CRC_TABLE = (() => { const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) { let c = i; for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[i] = c; }
  return t; })();
function crc32(u8) { let c = 0xFFFFFFFF;
  for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0; }

(async () => {
  // 三種 entry：可壓縮（走 deflate）／高熵（**必走 stored**）／高熵分段陣列（B2 的組合案）
  const compressible = 'A'.repeat(20000);                                  // deflate 必縮
  const highEntropy  = new Uint8Array(crypto.randomBytes(65536));          // deflate 必脹 ⇒ stored
  const pieceA = new Uint8Array(crypto.randomBytes(30000));
  const pieceB = new Uint8Array(crypto.randomBytes(30000));
  const entries = [
    { name: 'a_text.xml',   data: compressible },
    { name: 'b_random.bin', data: highEntropy },
    { name: 'c_pieces.bin', data: [pieceA, 'MID-STRING-SEGMENT', pieceB] }, // 混合分段
    { name: 'd_empty.txt',  data: '' },                                    // 空 entry 邊界
  ];
  const expected = new Map([
    ['a_text.xml',   Buffer.from(compressible)],
    ['b_random.bin', Buffer.from(highEntropy)],
    ['c_pieces.bin', Buffer.concat([Buffer.from(pieceA), Buffer.from('MID-STRING-SEGMENT'), Buffer.from(pieceB)])],
    ['d_empty.txt',  Buffer.alloc(0)],
  ]);

  const blob = await Engine._internals.makeZip(entries);
  const zip = Buffer.from(await blob.arrayBuffer());
  console.log(`zip 總長 ${zip.length} bytes`);

  // ---- 逐 local header 走訪（獨立解析，不用受測碼）----
  let off = 0, checked = 0, storedSeen = 0, deflateSeen = 0;
  while (off + 4 <= zip.length && zip.readUInt32LE(off) === 0x04034b50) {
    const method = zip.readUInt16LE(off + 8);
    const crcHdr = zip.readUInt32LE(off + 14);
    const clen   = zip.readUInt32LE(off + 18);
    const rlen   = zip.readUInt32LE(off + 22);
    const nlen   = zip.readUInt16LE(off + 26);
    const elen   = zip.readUInt16LE(off + 28);
    const name   = zip.toString('utf8', off + 30, off + 30 + nlen);
    const payload = zip.subarray(off + 30 + nlen + elen, off + 30 + nlen + elen + clen);

    const orig = expected.get(name);
    assert(orig !== undefined, `多出未預期 entry：${name}`);

    let restored;
    if (method === 0) {
      storedSeen++;
      assert.strictEqual(clen, rlen, `${name}: stored 但 clen(${clen}) != rlen(${rlen})＝B2 地雷還在`);
      restored = Buffer.from(payload);
    } else if (method === 8) {
      deflateSeen++;
      restored = zlib.inflateRawSync(payload);
    } else assert.fail(`${name}: 未知 method ${method}`);

    assert.strictEqual(restored.length, rlen, `${name}: 還原長度 ${restored.length} != header rlen ${rlen}`);
    assert(restored.equals(orig), `${name}: 還原內容 != 原始輸入`);
    assert.strictEqual(crc32(restored), crcHdr, `${name}: CRC 不符（header ${crcHdr.toString(16)}）`);
    console.log(`  ✓ ${name.padEnd(14)} method=${method} rlen=${rlen} clen=${clen} CRC ok`);
    checked++;
    off += 30 + nlen + elen + clen;
  }
  assert.strictEqual(checked, entries.length, `只驗到 ${checked}/${entries.length} 個 entry`);
  assert(storedSeen >= 1, '沒有任何 entry 走到 stored 路徑＝本測沒測到要測的東西（高熵料失效？）');
  assert(deflateSeen >= 1, '沒有任何 entry 走 deflate＝壓縮路徑也要在場');

  // ---- EOCD／central directory 由 miniz 級檢查代替：這裡至少驗 EOCD 存在且計數正確 ----
  const eocd = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  assert(eocd >= 0, '找不到 EOCD');
  assert.strictEqual(zip.readUInt16LE(eocd + 10), entries.length, 'EOCD entry 總數不符');

  console.log(`\nPASS：${checked} entries（stored×${storedSeen}／deflate×${deflateSeen}）header/內容/CRC/EOCD 全一致`);
})().catch(e => { console.error('FAIL：', e.message); process.exit(1); });
