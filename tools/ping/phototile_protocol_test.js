/* =====================================================================
   照片磚引擎協定單元測（C-1，2026-07-31）
   跑法：node tools/ping/phototile_protocol_test.js
   規則正本＝tools/ping/phototile_protocol.md；受測實作＝
   resources/web/phototile/engine_protocol.js（C++ 宿主逐條鏡像同一規則）。

   紀律：正向測只證「串得起來」，真正的價值在**反向測**——四項驗證
   （連號／塊數／總長度／SHA-256）每一項都要有一個「動手腳就必須紅」的案例。
   ===================================================================== */
'use strict';
const path = require('path');
const crypto = require('crypto');
const P = require(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'engine_protocol.js'));

const sha256 = bytes => crypto.createHash('sha256').update(Buffer.from(bytes)).digest('hex');

let pass = 0, fail = 0;
function check(name, fn){
  try { fn(); console.log(`  ✅ ${name}`); pass++; }
  catch (e) { console.log(`  ❌ ${name}\n     ${e.message}`); fail++; }
}
function assert(cond, msg){ if (!cond) throw new Error(msg || '斷言失敗'); }
function assertEq(got, want, msg){
  if (got !== want) throw new Error(`${msg || '值不符'}：期望 ${JSON.stringify(want)}、實得 ${JSON.stringify(got)}`);
}
/* 決定性測試資料（不用亂數＝失敗可重現） */
function makeBytes(n, seed){
  const out = new Uint8Array(n);
  let x = seed || 1;
  for (let i = 0; i < n; i++) { x = (x * 1103515245 + 12345) & 0x7fffffff; out[i] = x & 0xff; }
  return out;
}
/* 把 buildTransfer 的訊息序列餵進組裝器；回傳最終 state */
function feed(msgs, jobId){
  const asm = P.createAssembler(jobId || 'job-1', { sha256 });
  let st;
  for (const m of msgs) st = asm.accept(m);
  return st;
}

console.log('\n=== 照片磚引擎協定 v' + P.PROTOCOL_VERSION + ' 單元測 ===\n');

console.log('§1 base64 與分塊');
check('base64 往返一致（含 0x00/0xFF 邊界）', () => {
  const b = new Uint8Array([0, 1, 127, 128, 254, 255]);
  const back = P.base64ToBytes(P.bytesToBase64(b));
  assertEq(Buffer.from(back).toString('hex'), Buffer.from(b).toString('hex'), 'base64 往返');
});
check('chunkCount：邊界（0／剛好整除／多一位元組）', () => {
  assertEq(P.chunkCount(0, 100), 1, '空資料仍算 1 塊');
  assertEq(P.chunkCount(300, 100), 3, '整除');
  assertEq(P.chunkCount(301, 100), 4, '多一位元組');
});

console.log('\n§1.5 純 JS SHA-256 後備（不得與 node:crypto 有任何差異）');
check('標準向量：空字串／abc／448bit 邊界', () => {
  assertEq(P.sha256HexSync(new Uint8Array(0)),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', '空字串');
  assertEq(P.sha256HexSync(new Uint8Array([0x61,0x62,0x63])),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad', '"abc"');
  const s = 'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq';           // 56 bytes＝補位邊界
  assertEq(P.sha256HexSync(new Uint8Array(Buffer.from(s))),
    '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1', '56 位元組邊界');
});
check('與 node:crypto 對拍：長度 0…200 逐一比對', () => {
  for (let n = 0; n <= 200; n++) {
    const b = makeBytes(n, n + 1);
    assertEq(P.sha256HexSync(b), sha256(b), `長度 ${n}`);
  }
});
check('與 node:crypto 對拍：跨區塊長度（55/56/57/63/64/65/119/120/1MB+1）', () => {
  for (const n of [55, 56, 57, 63, 64, 65, 119, 120, 1024 * 1024 + 1]) {
    const b = makeBytes(n, 99);
    assertEq(P.sha256HexSync(b), sha256(b), `長度 ${n}`);
  }
});
check('翻一個位元組就變值（雪崩，證明不是常數回傳）', () => {
  const b = makeBytes(4096, 5);
  const h1 = P.sha256HexSync(b);
  b[2048] ^= 0x01;
  assert(h1 !== P.sha256HexSync(b), '改一位元組雜湊必須改變');
});

console.log('\n§2 正向：3MF 分塊往返（四項驗證全過）');
check('2.3MB 分塊往返後位元組與 SHA 全等', () => {
  const bytes = makeBytes(2 * 1024 * 1024 + 12345, 7);
  const st = feed(P.buildTransfer('job-1', bytes, sha256(bytes)), 'job-1');
  assert(!st.error, '不應有錯：' + JSON.stringify(st.error));
  assert(st.done, '應完成');
  assertEq(st.bytes.length, bytes.length, '總長度');
  assertEq(sha256(st.bytes), sha256(bytes), 'SHA-256');
});
check('96KB 預設分塊數＝ceil(size/96K)', () => {
  const bytes = makeBytes(300 * 1024, 3);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  const begin = msgs[0];
  assertEq(begin.chunks, Math.ceil(bytes.length / P.CHUNK_BYTES), '塊數');
  assertEq(msgs.length, begin.chunks + 2, 'begin＋N＋end');
});

console.log('\n§3 反向：四項驗證每項都要能擋（動手腳就必須紅）');
check('①連號：抽掉中間一塊 → protocol_chunk_order', () => {
  const bytes = makeBytes(400 * 1024, 11);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  msgs.splice(2, 1);                                   // 拿掉 index=1
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.CHUNK_ORDER, '錯誤碼');
});
check('①連號：兩塊對調 → protocol_chunk_order', () => {
  const bytes = makeBytes(400 * 1024, 12);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  const t = msgs[1]; msgs[1] = msgs[2]; msgs[2] = t;
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.CHUNK_ORDER, '錯誤碼');
});
check('②塊數：end 宣告塊數多一 → protocol_chunk_count', () => {
  const bytes = makeBytes(200 * 1024, 13);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  msgs[0].chunks += 1;                                  // begin 宣告多一塊、實際少送
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.CHUNK_COUNT, '錯誤碼');
});
check('③長度：分塊 length 欄位被竄改 → protocol_length_mismatch', () => {
  const bytes = makeBytes(200 * 1024, 14);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  msgs[1].length = msgs[1].length - 1;
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.LENGTH_MISMATCH, '錯誤碼');
});
check('③長度：begin.size 與實際不符 → protocol_length_mismatch', () => {
  const bytes = makeBytes(150 * 1024, 15);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  msgs[0].size += 10;
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.LENGTH_MISMATCH, '錯誤碼');
});
check('④SHA：內容被改一個位元組（長度不變）→ protocol_sha_mismatch', () => {
  const bytes = makeBytes(150 * 1024, 16);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  const tampered = P.base64ToBytes(msgs[1].base64);
  tampered[0] ^= 0xff;                                  // 只翻一個位元組＝長度與塊數全對，只有 SHA 抓得到
  msgs[1].base64 = P.bytesToBase64(tampered);
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.SHA_MISMATCH, '錯誤碼');
});
check('版本不符 → protocol_bad_version', () => {
  const bytes = makeBytes(1024, 17);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  msgs[0].v = 99;
  const st = feed(msgs, 'job-1');
  assertEq(st.error && st.error.code, P.PERR.BAD_VERSION, '錯誤碼');
});
check('jobId 不符（別的 job 的塊混進來）→ protocol_job_mismatch', () => {
  const bytes = makeBytes(1024, 18);
  const msgs = P.buildTransfer('job-A', bytes, sha256(bytes));
  const st = feed(msgs, 'job-B');
  assertEq(st.error && st.error.code, P.PERR.JOB_MISMATCH, '錯誤碼');
});
check('chunk 早於 begin → protocol_chunk_order', () => {
  const bytes = makeBytes(1024, 19);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes));
  const st = feed([msgs[1]], 'job-1');
  assertEq(st.error && st.error.code, P.PERR.CHUNK_ORDER, '錯誤碼');
});

console.log('\n§3.5 數值型別容錯（2026-07-31 閘門①實戰坑：boost ptree 把數字寫成字串）');
check('num()：字串數字／空值／非數字', () => {
  assertEq(P.num('1'), 1, '字串 "1"');
  assertEq(P.num(0), 0, '數字 0');
  assert(Number.isNaN(P.num(null)) && Number.isNaN(P.num(undefined)) && Number.isNaN(P.num('')), 'null/undefined/空字串應為 NaN');
  assert(Number.isNaN(P.num('abc')), '非數字應為 NaN');
});
check('宿主把 v／size／chunks／index／length 全寫成字串 → 仍能組裝成功', () => {
  const bytes = makeBytes(300 * 1024, 31);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes)).map(m => {
    const o = Object.assign({}, m);
    for (const k of ['v', 'size', 'chunks', 'index', 'length'])
      if (o[k] !== undefined) o[k] = String(o[k]);
    return o;
  });
  const st = feed(msgs, 'job-1');
  assert(!st.error, '不應有錯：' + JSON.stringify(st.error));
  assertEq(sha256(st.bytes), sha256(bytes), 'SHA-256');
});
check('容錯不得放水：字串型別下亂序／竄改仍要紅', () => {
  const bytes = makeBytes(300 * 1024, 32);
  const msgs = P.buildTransfer('job-1', bytes, sha256(bytes)).map(m => {
    const o = Object.assign({}, m);
    for (const k of ['v', 'size', 'chunks', 'index', 'length'])
      if (o[k] !== undefined) o[k] = String(o[k]);
    return o;
  });
  const swapped = msgs.slice(); const t = swapped[1]; swapped[1] = swapped[2]; swapped[2] = t;
  assertEq(feed(swapped, 'job-1').error?.code, P.PERR.CHUNK_ORDER, '亂序仍須擋');
  const tampered = P.buildTransfer('job-1', bytes, sha256(bytes)).map(m => Object.assign({}, m, { v: '1' }));
  const b = P.base64ToBytes(tampered[1].base64); b[0] ^= 0xff;
  tampered[1].base64 = P.bytesToBase64(b);
  assertEq(feed(tampered, 'job-1').error?.code, P.PERR.SHA_MISMATCH, '竄改仍須擋');
});

console.log('\n§4 影像注入分塊（C++→page）');
check('192K 字元分塊：塊數與字元總數一致、可還原', () => {
  const raw = makeBytes(700 * 1024, 21);
  const b64 = P.bytesToBase64(raw);
  const msgs = P.buildImageInjection('job-1', 'image/png', b64, 'x.png');
  const begin = msgs[0], end = msgs[msgs.length - 1];
  assertEq(begin.chunks, Math.ceil(b64.length / P.INJECT_CHARS), '塊數');
  assertEq(end.totalChars, b64.length, '字元總數');
  const joined = msgs.slice(1, -1).map(m => m.base64).join('');
  assertEq(joined.length, b64.length, '拼回字元數');
  assertEq(sha256(P.base64ToBytes(joined)), sha256(raw), '還原後位元組 SHA');
});
check('注入分塊序號連續（0..N-1）', () => {
  const b64 = P.bytesToBase64(makeBytes(500 * 1024, 22));
  const msgs = P.buildImageInjection('job-1', 'image/png', b64, null);
  msgs.slice(1, -1).forEach((m, i) => assertEq(m.index, i, `第 ${i} 塊序號`));
});

console.log('\n§5 環境快照過期即棄');
const envA = { printerPresetName: 'FD300 同進照片磚', nozzle: 0.4, plateId: 1, plateRevision: 7, projectRevision: 12 };
check('同一環境＝fresh', () => {
  assert(P.checkFresh(envA, Object.assign({}, envA)).fresh, '應判定新鮮');
});
check('換機（printerPresetName 變）＝丟棄', () => {
  const r = P.checkFresh(envA, Object.assign({}, envA, { printerPresetName: 'FF800 同進照片磚' }));
  assert(!r.fresh, '應丟棄'); assertEq(r.code, P.PERR.STALE_ENV, '錯誤碼');
});
check('換盤（plateRevision 變）＝丟棄', () => {
  assert(!P.checkFresh(envA, Object.assign({}, envA, { plateRevision: 8 })).fresh, '應丟棄');
});
check('換專案（projectRevision 變）＝丟棄', () => {
  assert(!P.checkFresh(envA, Object.assign({}, envA, { projectRevision: 13 })).fresh, '應丟棄');
});
check('宿主新增欄位＝自動納入比較（少一鍵就丟棄）', () => {
  const withExtra = Object.assign({}, envA, { plateEmpty: true });
  assert(!P.checkFresh(withExtra, envA).fresh, '鍵數不同應丟棄');
  assert(P.checkFresh(withExtra, Object.assign({}, withExtra)).fresh, '同鍵同值應新鮮');
});
check('缺快照＝視為過期（不得預設放行）', () => {
  assert(!P.checkFresh(null, envA).fresh, 'null 應丟棄');
  assert(!P.checkFresh(envA, null).fresh, 'null 應丟棄');
});
check('巢狀欄位差異也抓得到', () => {
  const a = { printer: { name: 'FD300', nozzle: 0.4 }, plateRevision: 1 };
  const b = { printer: { name: 'FD300', nozzle: 0.6 }, plateRevision: 1 };
  assert(!P.checkFresh(a, b).fresh, '巢狀值不同應丟棄');
});

console.log(`\n=== 結果：${pass} 過／${fail} 失敗 ===\n`);
process.exit(fail === 0 ? 0 : 1);
