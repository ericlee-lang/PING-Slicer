/* =====================================================================
   PhotoTileMatLib — 照片磚「材料庫」（規格 R6-14，Eric 2026-09-22 裁「照建議」）

   要解決的事：校正表原本**只有一格**（鍵 `ping_phototile_calib_dual_v1`），再匯入一張就蓋掉舊的，
   而且**不認材料身分、只比兩個 hex**（`engine.js` 的 `calibMatches()`）⇒ 使用者沒辦法「選一支已經
   校正過的料」，換料就等於重印校正片。本檔把它升成「一支料校一次就記著、之後用選的」。

   四條定死的規則（都是 R6-14 的四個子題，Eric 已裁，不要在這裡重開）：
     ① **身分＝`filament_id` ＋ 使用者自填標籤**（子題 1 裁 C）。
        `filament_id`（例 `GPINGABS`）改名不會變——本專案改過多次料名（0725 ABS 三支併一、0729 PLA-210、
        0817 3in1），而 `find_preset()` 不走 `renamed_from`，0725 T004 就因此讓整條連動靜默失效
        ⇒ **不能拿名稱當鍵**。但一個 preset ≠ 一捲料（同一支「PING PLA - 210」可能有白／黑／深灰三捲）
        ⇒ 再加一個使用者自填標籤才分得開。
        🔴 **量到的 hex 只當顯示與防呆，不當鍵**（同一支料不同批、不同機況量到的值會不一樣）。
     ② **庫的儲存單位是 pair（組合），料是 pair 的兩個端點**（子題 3 裁 B）。
        理由：量到的東西本身就是 pair 的資料；`R6-4` 定的失效單位也是 pair；四料 48 格＝6 pairs；
        S=1／S=0 那兩端本來就是單支料的實印色 ⇒ **存 pair 等於免費得到料**。
        反過來存料就得用模型回推 pair——那正是色彩校正要消滅的東西。
     ③ **換料的失效範圍＝只失效「含該支」的 pair**（`R6-4`）：換掉 B ⇒ A/B、B/C、B/D 失效，
        A/C、A/D、C/D **保留、不重測**。
     ④ **遷移不可要求使用者重印**（子題 2 附款）：舊鍵那一格要能被帶進來；舊表沒有 `filament_id`
        ⇒ 進來時 `fid:null`、`source:'legacy-hex'`，第一次在產圖流程選到它時請使用者「認領」
        給某兩支線材（一次性、可跳過）。**舊鍵不刪**（rollback 用），庫存在之後就不再寫它。

   🔴 **本檔不做色彩數學**。pts 只存「量到的 hex ＋ 那一格的配方 S」，要餵給引擎時用
   `toCalibTable()` 吐回**校正表原本的形狀**（料數／料／量測），讓 `engine.js` 的 `calibParseTable()`
   自己去算 lin——色彩數學只有引擎那一份，這裡不寫第二把尺（同 `dualLadder` 收成一份的理由）。

   儲存轉接層：頁面本來就跑在兩種環境——產品是 WebView（庫要落 `data_dir`，段 B 的 C++ 通道）、
   開發時是一般瀏覽器（`localStorage`）。**這不是預留後路**，既有碼已經是這個形狀
   （`calibTable.persisted` 存不進去時畫面誠實標示）。🔴 存不進去時照樣講出來，不靜默。
   ⚠ 段 B（C++ 通道）**不在車 1 範圍**；這裡先只有 localStorage 與 memory 兩個實作。
   ===================================================================== */
(function (root, factory) {
  const api = factory(root);
  root.PhotoTileMatLib = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
"use strict";

const SCHEMA = 1;
const LIB_KEY = 'ping_phototile_matlib_v1';
const LEGACY_KEY = 'ping_phototile_calib_dual_v1';   /* 🔴 只讀不刪：rollback 的唯一退路 */

/* 兩個分隔字元都是控制碼 ⇒ 不可能出現在 filament_id 或使用者填的標籤裡，
   也就不會有「標籤裡剛好有分隔字元 ⇒ 兩支不同的料算成同一支」這種靜默撞鍵。 */
const SEP_FIELD = '';   // 料的 fid 與 label 之間
const SEP_PAIR  = '';   // pair 的兩個端點之間

const KINDS = { DUAL: '雙料 8 階直立條', QUAD: '四料 48 格' };

function isHex(h){ return typeof h === 'string' && /^#[0-9A-Fa-f]{6}$/.test(h); }
function upHex(h){ return isHex(h) ? h.toUpperCase() : null; }

/* ---- 材料身分 ------------------------------------------------------- */
/* 🔴 hex 不進 key（R6-14 子題 1）。fid 缺席（＝舊表遷進來的）時 key 只剩標籤，
   而遷移時標籤預設帶原 hex ⇒ 那種格子仍然彼此分得開，但要「認領」之後才有真正的身分。 */
function matKey(m){
  if (!m) return '';
  const fid = m.fid == null ? '' : String(m.fid);
  const label = m.label == null ? '' : String(m.label);
  return fid + SEP_FIELD + label;
}
function makeMaterial(m){
  if (!m) throw new Error('材料不可為空');
  const hex = upHex(m.hex);
  const fid = (m.fid == null || m.fid === '') ? null : String(m.fid);
  const label = (m.label == null || m.label === '') ? (hex || '') : String(m.label);
  if (!fid && !label) throw new Error('材料至少要有 filament_id 或標籤其中之一');
  return { fid, label, hex };
}
/* pair 的 id ＝ 兩端 key 排序後 join ⇒ **與順序無關**（R6-4 的失效單位就是 pair，
   「A 配 B」與「B 配 A」是同一筆資料，不該在庫裡變成兩筆）。 */
function pairId(a, b){
  const ka = matKey(a), kb = matKey(b);
  return (ka <= kb ? ka + SEP_PAIR + kb : kb + SEP_PAIR + ka);
}

/* ---- 庫本體 --------------------------------------------------------- */
function emptyLib(){ return { schema: SCHEMA, pairs: [] }; }

/* 載進來的東西是使用者磁碟上的 JSON，可能被手改壞 ⇒ 一律過這支：壞的丟掉、好的留下，
   **不整份作廢**（整份作廢＝使用者失去所有校正資料，代價遠大於留下幾筆可疑的）。 */
function normalize(obj){
  const lib = emptyLib();
  if (!obj || typeof obj !== 'object') return lib;
  if (obj.schema !== SCHEMA) return lib;               // 版本不認得＝當空庫（不猜舊格式）
  const seen = new Set();
  const src = Array.isArray(obj.pairs) ? obj.pairs : [];
  for (const p of src){
    if (!p || typeof p !== 'object') continue;
    if (!p.a || !p.b) continue;
    let a, b;
    try { a = makeMaterial(p.a); b = makeMaterial(p.b); } catch (e) { continue; }
    const pts = Array.isArray(p.pts) ? p.pts.filter(pt =>
      pt && typeof pt.S === 'number' && isFinite(pt.S) && isHex(pt.hex)
    ).map(pt => ({ S: pt.S, hex: pt.hex.toUpperCase() })) : [];
    if (pts.length < 2) continue;                      // 少於 2 點內插不出曲線＝這筆沒有用
    const id = pairId(a, b);
    if (seen.has(id)) continue;                        // 同 id 只留第一筆（upsert 本來就不該產生重複）
    seen.add(id);
    lib.pairs.push({
      id, a, b,
      kind: typeof p.kind === 'string' ? p.kind : '',
      pts: pts.slice().sort((x, y) => y.S - x.S),      // S 由大到小＝a 多 → 少（與引擎 calibParseTable 同序）
      measuredAt: typeof p.measuredAt === 'string' ? p.measuredAt : null,
      source: p.source === 'legacy-hex' ? 'legacy-hex' : 'readback',
      claimedAt: typeof p.claimedAt === 'string' ? p.claimedAt : null,
    });
  }
  return lib;
}

function getPair(lib, id){
  if (!lib || !Array.isArray(lib.pairs)) return null;
  return lib.pairs.find(p => p.id === id) || null;
}
function findPair(lib, a, b){ return getPair(lib, pairId(a, b)); }

/* 同一對重量測 ⇒ **取代不新增**（原位取代，庫的順序穩定＝畫面上的清單不會跳動）。 */
function upsertPair(lib, pair){
  const norm = normalize({ schema: SCHEMA, pairs: [pair] });
  if (!norm.pairs.length) throw new Error('這筆 pair 不合法（料不完整，或量測點少於 2）');
  const p = norm.pairs[0];
  const i = lib.pairs.findIndex(x => x.id === p.id);
  if (i >= 0) lib.pairs[i] = p; else lib.pairs.push(p);
  return p;
}

/* 料的清單**從 pair 的端點推出來**，不另存一份（R6-14 子題 3 的理由：存 pair 免費得到料）。 */
function listMaterials(lib){
  const out = [], seen = new Set();
  if (!lib || !Array.isArray(lib.pairs)) return out;
  for (const p of lib.pairs) for (const m of [p.a, p.b]){
    const k = matKey(m);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ key: k, fid: m.fid, label: m.label, hex: m.hex });
  }
  return out;
}
/* 這支料配得到哪些料（＝哪些 pair 量過）。產圖流程要選一組料時就是查這個。 */
function partnersOf(lib, m){
  const k = matKey(m);
  const out = [];
  for (const p of (lib && lib.pairs) || []){
    if (matKey(p.a) === k) out.push({ pair: p, other: p.b });
    else if (matKey(p.b) === k) out.push({ pair: p, other: p.a });
  }
  return out;
}

/* 🔴 R6-4 逐字：換掉 B ⇒ **只**失效含 B 的 pair，其餘保留、不重測。 */
function dropMaterial(lib, m){
  const k = matKey(m);
  const removed = [], kept = [];
  const next = [];
  for (const p of (lib && lib.pairs) || []){
    if (matKey(p.a) === k || matKey(p.b) === k) removed.push(p.id);
    else { kept.push(p.id); next.push(p); }
  }
  lib.pairs = next;
  return { removed, kept };
}

/* ---- 從「校正表」建 pair ------------------------------------------- */
/* 入口是 engine.calibParseTable() 的產物，**不是**回讀頁的原始 JSON——
   解析（含色彩數學與合法性檢查）只有引擎那一份，本檔不重寫第二份。
   opt：{ materials:[料A, 料B, ...]（身分，可缺）, measuredAt, source } */
function pairFromDual(tbl, opt){
  opt = opt || {};
  if (!tbl || !Array.isArray(tbl.slots) || tbl.slots.length < 2 || !Array.isArray(tbl.pts))
    throw new Error('這不是解析過的雙料校正表');
  const mats = opt.materials || [];
  const a = makeMaterial(Object.assign({ hex: tbl.slots[0] }, mats[0] || {}));
  const b = makeMaterial(Object.assign({ hex: tbl.slots[1] }, mats[1] || {}));
  return {
    id: pairId(a, b), a, b,
    kind: opt.kind || tbl.kind || KINDS.DUAL,
    pts: tbl.pts.map(p => ({ S: p.S, hex: p.hex })),
    measuredAt: opt.measuredAt || null,
    source: opt.source || 'readback',
    claimedAt: null,
  };
}
/* 四料 48 格＝一次量到 6 個 pair（R6-2 附款：六對全有，不得砍成 24 格）。
   tbl ＝ engine.calibParseQuad() 的產物 {slots:[4 hex], pairs:[{i,j,pts}]}。 */
function pairsFromQuad(tbl, opt){
  opt = opt || {};
  if (!tbl || !Array.isArray(tbl.slots) || tbl.slots.length < 4 || !Array.isArray(tbl.pairs))
    throw new Error('這不是解析過的四料校正表');
  const mats = opt.materials || [];
  const mk = i => makeMaterial(Object.assign({ hex: tbl.slots[i] }, mats[i] || {}));
  return tbl.pairs.map(pr => {
    const a = mk(pr.i), b = mk(pr.j);
    return {
      id: pairId(a, b), a, b,
      kind: opt.kind || tbl.kind || KINDS.QUAD,
      pts: pr.pts.map(p => ({ S: p.S, hex: p.hex })),
      measuredAt: opt.measuredAt || null,
      source: opt.source || 'readback',
      claimedAt: null,
    };
  });
}

/* ---- 吐回引擎吃得下的校正表 ---------------------------------------- */
/* 🔴 吐的是**校正表原本的形狀**（料數／料／量測），交給 engine.calibParseTable() 去解析。
   這樣庫裡不必存 lin、不必算色彩數學，而且新舊兩條路（檔案匯入／從庫選）走的是同一支解析器。 */
function toCalibTable(pair){
  if (!pair) throw new Error('沒有這組料的校正資料');
  return {
    格式: 'PING 照片磚色彩校正表 v0（材料庫產出）',
    校正塊種類: pair.kind || '',
    料數: 2,
    料: [{ 槽: 'A', 色: pair.a.hex, 名: pair.a.label },
         { 槽: 'B', 色: pair.b.hex, 名: pair.b.label }],
    量測: pair.pts.map((p, i) => ({ 格: 'C' + (i + 1), 配方: { S: p.S }, 量到色: p.hex })),
  };
}
/* 四料：從庫裡湊出這四支料的六對。
   🔴 **湊不齊不補理論值**——湊不到的那一對就是沒有，回傳的 missing 讓呼叫端講給人聽（R6-16）。 */
function toQuadCalibTable(lib, materials){
  if (!Array.isArray(materials) || materials.length < 4) throw new Error('四料要四支料');
  const mats = materials.slice(0, 4).map(makeMaterial);
  const PAIRS = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]];
  const 量測 = [], missing = [], present = [];
  PAIRS.forEach(([i, j], r) => {
    const p = findPair(lib, mats[i], mats[j]);
    if (!p){ missing.push({ i, j, row: r + 1 }); return; }
    present.push({ i, j, row: r + 1, id: p.id });
    /* pair 在庫裡的 a/b 順序不保證等於 (i,j)——id 與順序無關，存的時候誰在前面是量測當下決定的。
       ⇒ 這裡要判一次方向，把 S 對回「i 這支料的佔比」，否則整對的曲線會頭尾顛倒（靜默錯表）。 */
    const flip = matKey(p.a) !== matKey(mats[i]);
    p.pts.forEach((pt, c) => {
      const S = flip ? (1 - pt.S) : pt.S;
      const wi = Math.round(S * 100);
      const w = [0, 0, 0, 0];
      w[i] = wi; w[j] = 100 - wi;
      量測.push({ 格: 'R' + (r + 1) + 'C' + (c + 1),
                  配方: { A: w[0], B: w[1], C: w[2], D: w[3] },
                  量到色: pt.hex });
    });
  });
  const table = {
    格式: 'PING 照片磚色彩校正表 v0（材料庫產出）',
    校正塊種類: KINDS.QUAD,
    料數: 4,
    料: mats.map((m, i) => ({ 槽: 'ABCD'[i], 色: m.hex, 名: m.label })),
    量測,
  };
  return { table, missing, present };
}

/* ---- 遷移（R6-14 子題 2 附款） ------------------------------------- */
/* tbl ＝ engine.calibParseTable(舊鍵裡那張表) 的產物。
   🔴 **已經有同一對的資料就不覆蓋**——庫裡那筆可能是後來重新量的（source:'readback'），
   拿舊的蓋掉＝把新量的資料丟掉。遷移因此是冪等的：跑幾次結果都一樣。 */
function migrateLegacy(lib, tbl, opt){
  opt = opt || {};
  const pair = pairFromDual(tbl, {
    materials: [{ fid: null, label: (tbl.slots[0] || '').toUpperCase() },
                { fid: null, label: (tbl.slots[1] || '').toUpperCase() }],
    measuredAt: opt.measuredAt || null,
    source: 'legacy-hex',
    kind: opt.kind || tbl.kind || KINDS.DUAL,
  });
  const exists = getPair(lib, pair.id);
  if (exists) return { added: false, pair: exists, why: '庫裡已經有這一對，不覆蓋' };
  upsertPair(lib, pair);
  return { added: true, pair: getPair(lib, pair.id), why: '' };
}

/* 這一格要不要請使用者認領？＝兩端至少有一端還沒有 filament_id。
   舊表遷進來的那一格一定落在這裡（R6-14 子題 2 附款）；
   ⚙ 在段 B（C++ 通道）接上之前，**頁面根本拿不到 filament_id**（index.html grep 零命中）
   ⇒ 這段期間新量的表也沒有 fid，同樣該認領。把判準放在「有沒有 fid」而不是「出身是不是舊表」，
   才不會讓那些新量的表靜默地永遠只能靠 hex 比對。 */
function needsClaim(pair){
  return !!(pair && (!pair.a.fid || !pair.b.fid));
}
/* 認領＝把 fid／標籤指給現在的哪兩支線材。**身分變了 ⇒ id 跟著變**（id 是身分算出來的），
   所以這裡是「移除舊 id、放進新 id」。⚠ 可跳過：不呼叫本支＝維持舊行為（只能靠 hex 比對）。 */
function claimPair(lib, id, aMat, bMat, opt){
  opt = opt || {};
  const old = getPair(lib, id);
  if (!old) throw new Error('庫裡沒有這一格：' + id);
  const a = makeMaterial(Object.assign({ hex: old.a.hex }, aMat || {}));
  const b = makeMaterial(Object.assign({ hex: old.b.hex }, bMat || {}));
  const next = {
    id: pairId(a, b), a, b, kind: old.kind,
    pts: old.pts,
    measuredAt: old.measuredAt,
    source: old.source,                 /* 🔴 保留 'legacy-hex'＝這筆的出身不會因為認領而變乾淨（可追溯） */
    claimedAt: opt.claimedAt || null,
  };
  lib.pairs = lib.pairs.filter(p => p.id !== id);
  return upsertPair(lib, next);
}

/* ---- 儲存轉接層 ----------------------------------------------------- */
/* impl＝{ name, readLib():string|null, writeLib(s):void, readLegacy():string|null }
   丟例外＝存不進去，由 save() 翻成 {persisted:false, why}。🔴 不吞例外、不靜默。 */
function memoryStorage(){
  let buf = null, legacy = null;
  return { name: 'memory',
    readLib: () => buf, writeLib: s => { buf = s; },
    readLegacy: () => legacy, _setLegacy: s => { legacy = s; } };
}
function localStorageStorage(ls){
  return { name: 'localStorage',
    readLib: () => ls.getItem(LIB_KEY),
    writeLib: s => ls.setItem(LIB_KEY, s),
    readLegacy: () => ls.getItem(LEGACY_KEY) };
}
/* 存不進去也要能用（讀得到就好），所以「沒有儲存區」不是錯誤，是一個會誠實講出來的狀態。 */
function nullStorage(why){
  return { name: 'none', _why: why,
    readLib: () => null, writeLib: () => { throw new Error(why); }, readLegacy: () => null };
}
function detectStorage(){
  try {
    const ls = (root && root.localStorage) ? root.localStorage : null;
    if (!ls) return nullStorage('這個環境沒有瀏覽器儲存區');
    const probe = '__ptml_probe__';
    ls.setItem(probe, '1'); ls.removeItem(probe);      // 無痕視窗會在這裡丟例外
    return localStorageStorage(ls);
  } catch (e) {
    return nullStorage('瀏覽器儲存區不可寫（' + (e && e.message || e) + '）');
  }
}

let STORAGE = null;
function getStorage(){ if (!STORAGE) STORAGE = detectStorage(); return STORAGE; }
function setStorage(impl){ STORAGE = impl || null; return getStorage(); }

function load(){
  const st = getStorage();
  let raw = null;
  try { raw = st.readLib(); } catch (e) { raw = null; }
  if (!raw) return emptyLib();
  try { return normalize(JSON.parse(raw)); } catch (e) { return emptyLib(); }
}
function save(lib){
  const st = getStorage();
  try { st.writeLib(JSON.stringify({ schema: SCHEMA, pairs: (lib && lib.pairs) || [] })); }
  catch (e) { return { persisted: false, why: '存不進' + st.name + '：' + (e && e.message || e) }; }
  return { persisted: true, why: '' };
}
/* 🔴 只讀，**不刪**。舊鍵留著＝rollback 的唯一退路；庫存在之後不再寫它（見檔頭規則④）。 */
function readLegacyRaw(){
  const st = getStorage();
  try {
    const s = st.readLegacy ? st.readLegacy() : null;
    return s ? JSON.parse(s) : null;
  } catch (e) { return null; }
}

return {
  SCHEMA, LIB_KEY, LEGACY_KEY, KINDS,
  matKey, makeMaterial, pairId,
  emptyLib, normalize, getPair, findPair, upsertPair,
  listMaterials, partnersOf, dropMaterial,
  pairFromDual, pairsFromQuad, toCalibTable, toQuadCalibTable,
  migrateLegacy, needsClaim, claimPair,
  memoryStorage, nullStorage, detectStorage, getStorage, setStorage,
  load, save, readLegacyRaw,
};
});
