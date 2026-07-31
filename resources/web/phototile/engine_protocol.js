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
         bytesToBase64, base64ToBytes, chunkCount,
         buildTransfer, createAssembler, buildImageInjection,
         envEqual, checkFresh };
});
