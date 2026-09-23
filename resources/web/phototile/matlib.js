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
   🆕 段 B（車 2，牌 `c-0923-ACC-21`）：產品路徑改落 **App 設定資料夾**（`hostStorage()`，見下方〈庫的家〉一節）；
      瀏覽器直開（開發）仍用 localStorage；兩種都存不進去才是 none（照樣講出來）。
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
      /* 車 3（段 F）：認領「一次性、可跳過」——跳過也要記住，否則每次選到都再問一次＝不是一次性。 */
      claimSkippedAt: typeof p.claimSkippedAt === 'string' ? p.claimSkippedAt : null,
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
/* 雙料：從庫裡取這兩支料那一對，照**槽位順序**（m0＝擠出機 1）吐回校正表（車 3 段 F，牌 c-0923-ACC-23）。
   pair 在庫裡的 a/b 順序是量測當下決定的，不保證等於槽位順序 ⇒ 反了就把 S 對回「m0 的佔比」並對調料色；
   不翻＝engine.calibMatches 比料色對不上（整段不套用），或整條曲線頭尾顛倒（靜默錯表，同 toQuadCalibTable 的理由）。 */
function toDualCalibTable(lib, m0, m1){
  const a = makeMaterial(m0), b = makeMaterial(m1);
  const p = findPair(lib, a, b);
  if (!p) return { table: null, pair: null };
  const flip = matKey(p.a) !== matKey(a);
  const A = flip ? p.b : p.a, B = flip ? p.a : p.b;
  return { pair: p, table: {
    格式: 'PING 照片磚色彩校正表 v0（材料庫產出）',
    校正塊種類: p.kind || '',
    料數: 2,
    料: [{ 槽: 'A', 色: A.hex, 名: A.label }, { 槽: 'B', 色: B.hex, 名: B.label }],
    量測: p.pts.map((pt, i) => ({ 格: 'C' + (i + 1),
                                  配方: { S: flip ? Math.round((1 - pt.S) * 100) / 100 : pt.S },
                                  量到色: pt.hex })),
  } };
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
  /* 🆕 車 3（段 F，牌 c-0923-ACC-23）：同一組量測點已經在庫裡（任何身分）＝這張舊表遷過了，不再加一次。
     為什麼要比內容：認領（claimPair）會把身分換成 filament_id＋標籤 ⇒ id 跟著變，只比 id 的話
     每次開工作室都會把舊鍵那張表再遷進來一次，清單上就多一組以色碼命名的重複項（段 F 瀏覽器實走抓到）。 */
  const pts = pair.pts.map(p => p.S + p.hex).join('|');
  const same = (lib.pairs || []).find(p => p.pts.map(x => x.S + x.hex).join('|') === pts);
  if (same) return { added: false, pair: same, why: '這張舊表的量測已經在庫裡（可能已經認領過）' };
  upsertPair(lib, pair);
  return { added: true, pair: getPair(lib, pair.id), why: '' };
}

/* 這一格要不要請使用者認領？＝兩端至少有一端還沒有 filament_id。
   舊表遷進來的那一格一定落在這裡（R6-14 子題 2 附款）；
   ⚙ 段 B（車 2）之後頁面拿得到「機上裝了哪幾支線材」（capability 的 filaments），但**校正片的哪一端是哪一支**
     仍要人指定（校正流程第一步／認領，車 3），程式不從目前的擠出機去猜——猜錯＝整筆資料掛錯身分，而且沒人會發現。
   ⇒ 所以匯入的表仍然沒有 fid，同樣該認領。把判準放在「有沒有 fid」而不是「出身是不是舊表」，
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

/* ---- 庫的家＝App 設定資料夾（段 B；R6-14 子題 2 裁 B：庫落 data_dir） ------------------
   產品路徑：頁面 ↔ C++ 走 `phototile_matlib_*` 四支訊息，檔案落
   `<data_dir>/phototile/material_library.json`（原子寫：.tmp 寫完才換上；換上前把舊檔留一份 .bak）。
   🔴 照**活著的** `phototile_image_begin|chunk|end` 抄四項驗證：①連號 ②塊數 ③總長度 ④上限。
      （`phototile_export_*` 別抄——它現在只剩校正片 3MF 在用，形狀是舊的。）
   🔴 `createSaveAssembler()` ＝ C++ 收件口的**參考模型**：規則只寫這一份，GUI_App.cpp 逐條鏡像；
      單元測的反向案例（亂序／少塊／長度竄改／超上限／壞 base64）打的就是它。
      **一次存檔只回一次結果**（在 end 那一刻）：中途壞掉就記下原因、後面的塊一律不收，到 end 才回報。
   ℹ️ 測試版有獨立 data root ⇒ 測試版與出貨版的材料庫各自一份（版本治理的必然結果，不是缺陷）。 */
/* 上限 512 KB 的由來：一對雙料 8 點約 350 bytes、一張四料 48 格（6 對）約 2 KB ⇒ 512 KB 約可放一千五百對，
   遠超過實際會用到的量；而讀檔回程是**一次** RunScript 注入（不分塊），上限壓小就不必再做一套分塊回程。
   超過時送出端先擋、並把原因講出來（不是默默存不進去）。 */
const HOST_MAX_BYTES   = 524288;            // 🔴 同值住 GUI_App.cpp（max_matlib_bytes）；改要一起改
const HOST_MAX_CHUNKS  = 4096;              // 🔴 同上
const HOST_CHUNK_BYTES = 48 * 1024;         // 可被 3 整除 ⇒ 每一塊的 base64 中段不會有 padding
const CMD = { LOAD: 'phototile_matlib_load',
              SAVE_BEGIN: 'phototile_matlib_save_begin',
              SAVE_CHUNK: 'phototile_matlib_save_chunk',
              SAVE_END:   'phototile_matlib_save_end' };

function utf8Encode(s){
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(String(s));
  return Uint8Array.from(Buffer.from(String(s), 'utf8'));
}
/* fatal：壞掉的 UTF-8 直接丟例外，不要靜默換成 U+FFFD（那會把壞檔當成好檔再存回去）。 */
function utf8Decode(u8){ return new TextDecoder('utf-8', { fatal: true }).decode(u8); }
function bytesToB64(u8){
  if (typeof Buffer !== 'undefined') return Buffer.from(u8).toString('base64');
  let s = '';
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(s);
}
/* 壞掉的 base64 一律丟例外——不可以靜默解成一段比較短的資料（長度驗證就是靠它才抓得到）。 */
function b64ToBytes(b64){
  if (typeof b64 !== 'string' || b64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(b64))
    throw new Error('base64 格式不合');
  if (typeof Buffer !== 'undefined') return Uint8Array.from(Buffer.from(b64, 'base64'));
  const s = atob(b64); const u8 = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u8[i] = s.charCodeAt(i);
  return u8;
}

/* 頁面 → App：把整份庫（JSON 字串）切成 begin／chunk…／end。超過上限在這裡就擋、並講出來。 */
function buildSaveMessages(text, chunkBytes){
  const bytes = utf8Encode(text);
  if (!bytes.length) throw new Error('材料庫內容是空的');
  if (bytes.length > HOST_MAX_BYTES)
    throw new Error('材料庫超過 ' + (HOST_MAX_BYTES / 1024) + ' KB 上限（' + bytes.length + ' bytes）');
  const cb = chunkBytes || HOST_CHUNK_BYTES;
  const chunks = Math.ceil(bytes.length / cb);
  const out = [{ command: CMD.SAVE_BEGIN, data: { size: bytes.length, chunks } }];
  for (let i = 0; i < chunks; i++)
    out.push({ command: CMD.SAVE_CHUNK,
               data: { index: i, base64: bytesToB64(bytes.subarray(i * cb, Math.min(bytes.length, (i + 1) * cb))) } });
  out.push({ command: CMD.SAVE_END, data: { size: bytes.length, chunks } });
  return out;
}

/* C++ 收件口的參考模型。accept(msg) 回傳：
     {ok:true, done:false}              收下這一步
     {ok:true, done:true, bytes}        收齊，可以落檔
     {ok:false, code, why, report}      這一步不收；report:true＝這一刻要回報頁面（只有 end 會是 true）
   code：limit（④上限）／order（①連號）／decode（壞 base64）／length（③總長度）／count（②塊數）／idle（沒有 begin）。
   🔴 中途壞掉＝整批作廢、緩衝丟掉，**絕不半套落檔**（半套＝使用者的校正資料被截斷，而且不報錯）。 */
function createSaveAssembler(maxBytes, maxChunks){
  const cap = maxBytes || HOST_MAX_BYTES, capN = maxChunks || HOST_MAX_CHUNKS;
  let state = 'idle', size = 0, chunks = 0, next = 0, parts = [], got = 0, failCode = '', failWhy = '';
  const clear = () => { size = 0; chunks = 0; next = 0; parts = []; got = 0; };
  const fail = (code, why) => { clear(); state = 'failed'; failCode = code; failWhy = why;
                                return { ok: false, code, why, report: false }; };
  return {
    accept(m){
      const cmd = m && m.command, d = (m && m.data) || {};
      if (cmd === CMD.SAVE_BEGIN){
        clear(); state = 'idle'; failCode = ''; failWhy = '';
        const s = Number(d.size), c = Number(d.chunks);
        if (!Number.isInteger(s) || s <= 0 || s > cap) return fail('limit', '材料庫大小不合法或超過上限（' + d.size + '）');
        if (!Number.isInteger(c) || c <= 0 || c > capN || c > s) return fail('limit', '分塊數不合法（' + d.chunks + '）');
        state = 'active'; size = s; chunks = c;
        return { ok: true, done: false };
      }
      if (cmd === CMD.SAVE_CHUNK){
        if (state !== 'active') return { ok: false, code: state === 'failed' ? failCode : 'idle', why: '這一批已作廢或沒有開始', report: false };
        if (Number(d.index) !== next || typeof d.base64 !== 'string' || !d.base64)
          return fail('order', '分塊亂序或是空的（期望第 ' + next + ' 塊，收到 ' + d.index + '）');
        let u8;
        try { u8 = b64ToBytes(d.base64); } catch (e) { return fail('decode', '分塊內容解不開'); }
        if (!u8.length || got + u8.length > size) return fail('length', '累計長度超過宣告的 ' + size + ' bytes');
        parts.push(u8); got += u8.length; next++;
        return { ok: true, done: false };
      }
      if (cmd === CMD.SAVE_END){
        if (state === 'failed'){ const r = { ok: false, code: failCode, why: failWhy, report: true }; state = 'idle'; return r; }
        if (state !== 'active') return { ok: false, code: 'idle', why: '沒有進行中的存檔', report: true };
        if (next !== chunks){ const r = fail('count', '分塊數不符（收到 ' + next + '／宣告 ' + chunks + '）'); state = 'idle'; r.report = true; return r; }
        if (got !== size){ const r = fail('length', '總長度不符（收到 ' + got + '／宣告 ' + size + '）'); state = 'idle'; r.report = true; return r; }
        const bytes = new Uint8Array(size); let o = 0;
        for (const p of parts){ bytes.set(p, o); o += p.length; }
        clear(); state = 'idle';
        return { ok: true, done: true, bytes };
      }
      return { ok: false, code: 'unknown', why: '不認得的訊息：' + cmd, report: false };
    }
  };
}

/* 讀進來的原文 → 庫。和 load() 的差別：**讀不懂要講出來**（ok:false＋why），不靜默當成空庫——
   App 那一份若被手改壞，呼叫端要知道「不能拿空庫去蓋它」。原文是 null／空字串＝還沒有庫（ok:true）。 */
function parseLib(raw){
  if (raw == null || raw === '') return { ok: true, lib: emptyLib(), why: '' };
  let obj;
  try { obj = JSON.parse(raw); } catch (e) { return { ok: false, lib: emptyLib(), why: '材料庫檔案不是合法的 JSON' }; }
  if (!obj || typeof obj !== 'object' || obj.schema !== SCHEMA)
    return { ok: false, lib: emptyLib(), why: '材料庫檔案的版本不認得（schema ' + (obj && obj.schema) + '）' };
  return { ok: true, lib: normalize(obj), why: '' };
}
/* 把 from 裡、into 還沒有的 pair 併進 into。🔴 **不覆蓋**已有的那一筆（into 那筆可能是後來重新量的）。
   用途：①App 讀檔回來之前使用者先匯入的表 ②車 1 期間存在瀏覽器儲存區的庫——都要併進 App 那一份。 */
function mergeLib(into, from){
  let added = 0;
  for (const p of (from && from.pairs) || []){
    if (getPair(into, p.id)) continue;
    upsertPair(into, p); added++;
  }
  return added;
}

/* App 那一份的儲存實作。send(command, data)＝頁面的 sendSlicerMessage；
   ls＝瀏覽器儲存區，**只為了讀舊資料**（舊鍵、車 1 期間的庫），兩者都要併進 App 那一份，只讀不刪。
   寫入是非同步的：writeLib 回 'pending'，結果由 App 回推 matlibSaved({ok, message})。 */
function hostStorage(send, ls){
  let buf = null;
  const lsGet = k => { try { return ls ? ls.getItem(k) : null; } catch (e) { return null; } };
  return { name: 'App 設定資料夾', isHost: true,
    readLib: () => buf,
    writeLib: s => { const msgs = buildSaveMessages(s); msgs.forEach(m => send(m.command, m.data)); buf = s; return 'pending'; },
    readLegacy: () => lsGet(LEGACY_KEY),
    readBrowserLib: () => lsGet(LIB_KEY),
    requestLoad: () => send(CMD.LOAD, {}),
    /* App 回來的讀檔結果 {ok, exists, base64, message} → 放進緩衝；回傳 {ok, why}。 */
    acceptLoad: msg => {
      if (!msg || msg.ok !== true) return { ok: false, why: (msg && msg.message) || 'App 讀不到材料庫' };
      if (!msg.exists){ buf = null; return { ok: true, why: '' }; }
      try { buf = utf8Decode(b64ToBytes(String(msg.base64 || ''))); return { ok: true, why: '' }; }
      catch (e) { buf = null; return { ok: false, why: '材料庫檔案讀回來是壞的（' + (e && e.message || e) + '）' }; }
    } };
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
/* 回傳 {persisted, why}（車 1 的形狀，一個字不動——phototile_calib_test.js 釘住了它）；
   只有 App 那條會多一個 pending:true＝已送給 App、結果還沒回來（App 會回推 matlibSaved）。
   呼叫端**不可把 pending 當成失敗**，也不可把它當成已存好。 */
function save(lib){
  const st = getStorage();
  let r;
  try { r = st.writeLib(JSON.stringify({ schema: SCHEMA, pairs: (lib && lib.pairs) || [] })); }
  catch (e) { return { persisted: false, why: '存不進' + st.name + '：' + (e && e.message || e) }; }
  if (r === 'pending') return { persisted: false, pending: true, why: '' };
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
  pairFromDual, pairsFromQuad, toCalibTable, toDualCalibTable, toQuadCalibTable,
  migrateLegacy, needsClaim, claimPair,
  memoryStorage, nullStorage, detectStorage, getStorage, setStorage,
  load, save, readLegacyRaw,
  HOST_MAX_BYTES, HOST_MAX_CHUNKS, HOST_CHUNK_BYTES, CMD,
  buildSaveMessages, createSaveAssembler, hostStorage, parseLib, mergeLib,
  utf8Encode, utf8Decode, bytesToB64, b64ToBytes,
};
});
