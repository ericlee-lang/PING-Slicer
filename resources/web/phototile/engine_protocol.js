/* =====================================================================
   PhotoTileProtocol — 照片磚 C-1 job 關聯協定（2026-07-31，照片磚線 PT）
   隱形引擎頁（engine.html）↔ C++ 宿主（PhotoTileEngineHost）之間的訊息框架與驗證。

   為什麼要獨立成一支：協定的「驗證規則」兩端各寫一次就會漂移（C-0 §3.3 的
   宿主原型即因 oracle 不完整被 Codex F-05 抓到）。本檔＝JS 端唯一實作，
   C++ 端逐條鏡像；規則正本＝tools/ping/phototile_protocol.md。
   本檔零 DOM、零計時器 ⇒ Node 可直接 require 跑單元測。
   ===================================================================== */
(function (root, factory) {
  const api = factory();
  root.PhotoTileProtocol = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
"use strict";

const PROTOCOL_VERSION = 1;
const CHUNK_BYTES      = 96 * 1024;   // 3MF 回傳分塊（C-0 §3.1 實測 2.3MB→24 塊／127ms）
const INJECT_CHARS     = 192 * 1024;  // 影像注入分塊字元數（＝WebViewDialog.cpp:333 現值）
const READY_TIMEOUT_MS = 15000;       // ready 握手逾時（C-0 §3.2 noready 負測即此值）

/* 訊息種類（host→page 用 cmd、page→host 用 type；兩邊都帶 v＝協定版本） */
const CMD  = { PING:'ping', GENERATE:'generate', CANCEL:'cancel',
               IMAGE_BEGIN:'imageBegin', IMAGE_CHUNK:'imageChunk', IMAGE_END:'imageEnd' };
const MSG  = { READY:'ready', PONG:'pong', PROGRESS:'progress', IMAGE_ACK:'imageAck',
               RESULT:'result', BEGIN:'begin', CHUNK:'chunk', END:'end',
               ERROR:'error', CANCEL_ACK:'cancelAck', SUPERSEDED:'superseded' };

/* 協定層錯誤碼（引擎層錯誤碼＝engine.js 的 ERR，兩者不重疊） */
const PERR = { BAD_MESSAGE:'protocol_bad_message', BAD_VERSION:'protocol_bad_version',
               UNKNOWN_CMD:'protocol_unknown_cmd', CHUNK_ORDER:'protocol_chunk_order',
               CHUNK_COUNT:'protocol_chunk_count', LENGTH_MISMATCH:'protocol_length_mismatch',
               SHA_MISMATCH:'protocol_sha_mismatch', JOB_MISMATCH:'protocol_job_mismatch',
               NO_IMAGE:'protocol_no_image', STALE_ENV:'protocol_stale_env' };

/* ================= base64（無 DOM 依賴，Node/瀏覽器同一份） ================= */
function bytesToBase64(bytes){
  if (typeof Buffer !== 'undefined') return Buffer.from(bytes).toString('base64');
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
function base64ToBytes(b64){
  if (typeof Buffer !== 'undefined') return new Uint8Array(Buffer.from(b64, 'base64'));
  const bin = atob(b64); const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/* ================= SHA-256（純 JS 後備） =================
   為什麼要自己寫一份：SHA-256 是四項驗證裡唯一能抓「長度塊數全對、內容被改」的一項，
   不能讓它有「環境沒有 crypto.subtle 就自動跳過」的空門。宿主端也因此可以要求
   **必須**有 digest（沒有＝協定錯誤）。與 crypto.subtle 的結果在單元測中對拍。 */
const K256 = [
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
function sha256HexSync(bytes){
  const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const len = bytes.length;
  const padded = new Uint8Array((((len + 8) >> 6) + 1) << 6);
  padded.set(bytes);
  padded[len] = 0x80;
  const bitLenHi = Math.floor(len / 0x20000000);
  const bitLenLo = (len << 3) >>> 0;
  const dv = new DataView(padded.buffer);
  dv.setUint32(padded.length - 8, bitLenHi, false);
  dv.setUint32(padded.length - 4, bitLenLo, false);
  const w = new Uint32Array(64);
  const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0;
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const s0 = (rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3)) >>> 0;
      const s1 = (rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10)) >>> 0;
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,hh] = h;
    for (let i = 0; i < 64; i++) {
      const S1 = (rotr(e,6) ^ rotr(e,11) ^ rotr(e,25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (hh + S1 + ch + K256[i] + w[i]) >>> 0;
      const S0 = (rotr(a,2) ^ rotr(a,13) ^ rotr(a,22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (S0 + maj) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0]=(h[0]+a)>>>0; h[1]=(h[1]+b)>>>0; h[2]=(h[2]+c)>>>0; h[3]=(h[3]+d)>>>0;
    h[4]=(h[4]+e)>>>0; h[5]=(h[5]+f)>>>0; h[6]=(h[6]+g)>>>0; h[7]=(h[7]+hh)>>>0;
  }
  return h.map(x => x.toString(16).padStart(8, '0')).join('');
}

/* ================= 3MF 回傳分塊 ================= */
function chunkCount(byteLength, chunkBytes){
  return Math.max(1, Math.ceil(byteLength / (chunkBytes || CHUNK_BYTES)));
}
/* 產生 begin/chunk/end 三段訊息（page→host）。sha256 由呼叫端算好傳入＝
   本檔不綁 crypto.subtle（Node 測試以 node:crypto 餵同一值）。 */
function buildTransfer(jobId, bytes, sha256, chunkBytes){
  const CH = chunkBytes || CHUNK_BYTES;
  const chunks = chunkCount(bytes.length, CH);
  const msgs = [{ v: PROTOCOL_VERSION, type: MSG.BEGIN, jobId, size: bytes.length, chunks, sha256 }];
  for (let i = 0; i < chunks; i++) {
    const slice = bytes.subarray(i * CH, Math.min(bytes.length, (i + 1) * CH));
    msgs.push({ v: PROTOCOL_VERSION, type: MSG.CHUNK, jobId, index: i, length: slice.length,
                base64: bytesToBase64(slice) });
  }
  msgs.push({ v: PROTOCOL_VERSION, type: MSG.END, jobId, sha256, chunks, size: bytes.length });
  return msgs;
}

/* ================= 宿主端組裝器（C++ 端逐條鏡像的規則） =================
   紀律：**收齊 end 且四項驗證全過才算 success**（塊數／連號／總長度／SHA-256）。
   任一不符＝丟棄整份、回報協定錯誤，不得半成品上盤。 */
function createAssembler(jobId, opts){
  const state = { jobId, size: 0, chunks: 0, sha256: null, received: 0,
                  parts: [], done: false, error: null, bytes: null };
  const fail = (code, message) => { state.error = { code, message }; state.done = true; return state; };
  return {
    state,
    accept(msg){
      if (state.done && state.error) return state;
      if (!msg || typeof msg !== 'object') return fail(PERR.BAD_MESSAGE, '訊息不是物件');
      if (msg.v !== PROTOCOL_VERSION) return fail(PERR.BAD_VERSION, `協定版本不符（收到 ${msg.v}）`);
      if (msg.jobId !== jobId) return fail(PERR.JOB_MISMATCH, `jobId 不符（期望 ${jobId}、收到 ${msg.jobId}）`);
      if (msg.type === MSG.BEGIN) {
        state.size = msg.size; state.chunks = msg.chunks; state.sha256 = msg.sha256 || null;
        state.parts = new Array(msg.chunks).fill(null); state.received = 0;
        return state;
      }
      if (msg.type === MSG.CHUNK) {
        if (!state.parts.length) return fail(PERR.CHUNK_ORDER, 'chunk 早於 begin');
        if (msg.index !== state.received)
          return fail(PERR.CHUNK_ORDER, `分塊序號不連續（期望 ${state.received}、收到 ${msg.index}）`);
        const bytes = base64ToBytes(msg.base64);
        if (typeof msg.length === 'number' && bytes.length !== msg.length)
          return fail(PERR.LENGTH_MISMATCH, `分塊 ${msg.index} 長度不符（宣告 ${msg.length}、實得 ${bytes.length}）`);
        state.parts[msg.index] = bytes; state.received++;
        return state;
      }
      if (msg.type === MSG.END) {
        if (state.received !== state.chunks)
          return fail(PERR.CHUNK_COUNT, `塊數不符（宣告 ${state.chunks}、實收 ${state.received}）`);
        const total = state.parts.reduce((a, b) => a + b.length, 0);
        if (total !== state.size)
          return fail(PERR.LENGTH_MISMATCH, `總長度不符（宣告 ${state.size}、實得 ${total}）`);
        const out = new Uint8Array(total); let off = 0;
        for (const p of state.parts) { out.set(p, off); off += p.length; }
        state.bytes = out;
        const expect = msg.sha256 || state.sha256;
        if (expect && opts && typeof opts.sha256 === 'function') {
          const got = opts.sha256(out);
          if (got !== expect) return fail(PERR.SHA_MISMATCH, `SHA-256 不符（宣告 ${expect}、實得 ${got}）`);
        }
        state.done = true;
        return state;
      }
      return fail(PERR.BAD_MESSAGE, `組裝器不接受的訊息型別 ${msg.type}`);
    }
  };
}

/* ================= 影像注入分塊（C++→page；鏡像 SendPendingPhotoTileImage） ================= */
function buildImageInjection(jobId, mime, base64, name, chunkChars){
  const CH = chunkChars || INJECT_CHARS;
  const chunks = Math.max(1, Math.ceil(base64.length / CH));
  const msgs = [{ v: PROTOCOL_VERSION, cmd: CMD.IMAGE_BEGIN, jobId, mime, name: name || null,
                  totalChars: base64.length, chunks }];
  for (let i = 0; i < chunks; i++)
    msgs.push({ v: PROTOCOL_VERSION, cmd: CMD.IMAGE_CHUNK, jobId, index: i,
                base64: base64.slice(i * CH, (i + 1) * CH) });
  msgs.push({ v: PROTOCOL_VERSION, cmd: CMD.IMAGE_END, jobId, totalChars: base64.length, chunks });
  return msgs;
}

/* ================= 環境快照（C-1：過期即棄） =================
   生成期間換機／換盤／關專案 ⇒ 舊結果不得寫回新情境（Codex #7）。
   宿主在 generate 時帶入 env，引擎原封回傳；上盤前再比一次。
   欄位由宿主定義，本函式只做「逐鍵嚴格相等」＝新增欄位自動納入比較。 */
function envEqual(a, b){
  if (!a || !b) return false;
  const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  if (ka.length !== kb.length) return false;
  for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return false;
  for (const k of ka) {
    const va = a[k], vb = b[k];
    if (va === null || typeof va !== 'object') { if (va !== vb) return false; }
    else if (!envEqual(va, vb)) return false;
  }
  return true;
}
/* 上盤前的最終閘門：結果的 env 必須與「現在的」env 相同，否則丟棄。 */
function checkFresh(resultEnv, currentEnv){
  if (!resultEnv || !currentEnv) return { fresh: false, code: PERR.STALE_ENV, message: '缺少環境快照＝視為過期' };
  return envEqual(resultEnv, currentEnv)
    ? { fresh: true }
    : { fresh: false, code: PERR.STALE_ENV, message: '環境已變更（換機／換盤／換專案）＝結果丟棄' };
}

return { PROTOCOL_VERSION, CHUNK_BYTES, INJECT_CHARS, READY_TIMEOUT_MS,
         CMD, MSG, PERR,
         bytesToBase64, base64ToBytes, chunkCount, sha256HexSync,
         buildTransfer, createAssembler, buildImageInjection,
         envEqual, checkFresh };
});
