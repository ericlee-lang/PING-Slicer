/* =====================================================================
   PhotoTileMatFlow — 照片磚「產圖流程 × 校正流程」（段 F，車 3；牌 c-0923-ACC-23）

   規格正本＝`照片磚_核心規格.md` R6-13～R6-16、R6-7 附款；動線正本＝`原型_照片磚料與校正_v3_20260922.html`。
   本檔只做兩件事：①產圖流程第 1 步「選顏色」（從材料庫選、硬閘門、色階上限、槽位）②校正流程五步的畫面狀態。
   色彩數學一行都不寫——判「一對能不能用」用引擎的 calibQuadPairGuard、四料跨幅用引擎的 quadCandidates、
   排槽位用引擎的 hexLstar；庫的讀寫用 PhotoTileMatLib。**這條線被兩份實作咬過三次，不寫第二把尺。**

   三條定死的規則（Eric 2026-09-22／23 已裁，不要在這裡重開）：
     ① **料 → 圖**（R6-16）：產圖流程的顏色只從材料庫來；沒量過的料不在這個清單裡（推論①）。
        選第二支起照「這一對有沒有一起校正過」判——庫存的單位是 pair（R6-14 子題 3），
        兩支各自校正過、但沒有一起校正過，那一對的混色一樣沒人量過。
     ② **選不到要講為什麼、並給出口**（`ping-ux` FBK-11／HIE-50）：選不到的列不隱藏、不純灰，
        列上直接寫原因；點下去再講一次，並給「去校正一組料」。
     ③ **兩條流程分開**（R6-15 附款）：產圖流程不出現六對矩陣／「沒校正會怎樣」；兩條流程共用的只有材料庫。
   ⚙ 「這組料最多做得出 N 階」照原型 v3 放在產圖流程（R6-7 附款；四料用 48 格候選的**全域**跨幅，
     不照原型「頭尾兩支」的簡化寫法——R6-7 附款 Q4 明寫）。

   🆕 T061（牌 c-0924-ACC-27；發包單〈九〉9-6 分車表 T061 那一列；動線與長相正本＝`原型_照片磚材料庫管理_20260923.html`，
      Eric 2026-09-23「好，原型 OK」；原型的 JS 是示意，資料照 matlib.js schema 2）：
     ④ **身分＝料種＋顏色名**，三處「指定材料」＝同一個元件（mpHtml）：校正第 1 步／匯入校正表之後（**匯入不再跳過確認**）／
        舊資料第一次開（問一次；清單上的「指定…」同一個元件）。名字任取、**不擋**，只提示重複（Eric：「如果我沒有選擇它的話，
        那它就是一隻新的材料」）；唯一擋的＝同一組兩支同名。色塊只放量到的色，**不拿擠出機設定色充數**。
     ⑤ 右欄這一塊：收起時只寫「擠出機 1 ■白　擠出機 2 ■深灰」＋「換一組…」、**不放步驟號**；展開＝「選顏色」＋料單，
        料單右上「新增或更新：去校正一組料／匯入校正表…」＝跟選料**平行**（Eric：「選擇材料跟校正其實是平行的，它沒有先後順序」）。
        擠出機顏色**只寫這一處**（列印模擬標題列的色塊 chipsHtml 退場：「資訊好像重疊了，是否留一個就好了呢？」）。
     ⛔ 封存、匯出、統一匯入（自動分辨材料庫檔）、還原上一版、匯入撞同一組逐組問＝T062，不在這裡。
   ===================================================================== */
(function (root, factory) {
  const api = factory(root);
  root.PhotoTileMatFlow = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
"use strict";

const NEED = { dual: 2, quad: 4 };
const LEVELS_MAX = 8;                        // 引擎 clamp 同值（Eric 2026-08-02 裁 B）
const SEL_KEY = 'ping_phototile_matsel_v1';   // 上次選的那組（每台電腦各自的便利設定；存不進去也照常運作）

function M(){ return root.PhotoTileMatLib; }
function E(){ return root.PhotoTileEngine; }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c]); }

/* ================= 純邏輯（node 測得到） ================= */

/* 一對料能不能用＝引擎 calibQuadPairGuard（R6-7 附款：跨幅 < 4 L* 擋、非單調擋；≥ 4 只壓階數）。
   雙料也用同一支：雙料的 calibGenLadder 另有「跨幅 < K」那一道，但色階數先被壓到 floor(跨幅)，那一道就永遠不會觸發。 */
function pairVerdict(lib, a, b){
  const p = M().findPair(lib, a, b);
  if (!p) return { ok: false, kind: 'missing', why: '沒有一起校正過', pair: null };
  let pts;
  try { pts = E().calibParseTable(M().toCalibTable(p)).pts; }
  catch (e) { return { ok: false, kind: 'bad', why: '這一對的校正資料讀不到（' + (e && e.message || e) + '）', pair: p }; }
  const g = E().calibQuadPairGuard(pts, LEVELS_MAX);
  const human = s => String(s || '').replace(/L\* ?/g, '亮度');   // 七律#4 講人話：引擎訊息的 L* 在畫面上改說「亮度」
  return { ok: g.ok, kind: g.ok ? 'ok' : 'blocked', why: human(g.blocked), warn: human(g.warnOnly),
           span: g.span, maxLevels: Math.min(LEVELS_MAX, g.maxLevels), pair: p };
}

/* 產圖流程第 1 步的清單。picked＝已點的料（matKey，點的順序）。
   選滿之後再點另一支＝**從那支重新開始選**（原型 v3 是「擠掉最早點的那支」；但庫存的是 pair，
   擠掉的剛好是跟新那支量過的那一支時，新那支會被標成「選不到」而其實選得到——那是假的閘門）。
   列的順序**固定照庫**（不把選不到的搬到後面）：點一下就重排＝使用者每點一次都要重新找一遍。 */
function choices(lib, mode, picked){
  const need = NEED[mode] || 2;
  const mats = M().listMaterials(lib);
  const byKey = new Map(mats.map(m => [m.key, m]));
  const pk = (picked || []).filter(k => byKey.has(k)).slice(0, need);
  const keep = (pk.length >= need ? [] : pk).map(k => byKey.get(k));
  const rows = mats.map(m => {
    const i = pk.indexOf(m.key);
    if (i >= 0) return { mat: m, state: 'picked', order: i, why: '' };
    for (const q of keep){
      const v = pairVerdict(lib, m, q);
      if (!usable(mode, v)) return { mat: m, state: 'no', why: v.kind === 'missing'
        ? ('沒和「' + q.label + '」一起校正過' + (mode === 'quad' ? '（四料要六對都一起量過）' : ''))
        : ('和「' + q.label + '」這一對不能用：' + v.why) };
    }
    if (!keep.length && !M().partnersOf(lib, m).some(x => usable(mode, pairVerdict(lib, m, x.other))))
      return { mat: m, state: 'no', why: '它量過的組合都不能用（到校正流程重新校正）' };
    return { mat: m, state: 'ok', why: '' };
  });
  return { need, picked: pk, rows, ready: pk.length === need };
}
/* 一對在這個料數下算不算「可以一起選」：
   雙料＝整張磚就是這一對 ⇒ 要通過護欄（R6-7 附款：跨幅 < 4 擋、非單調擋）。
   四料＝**有一起量過就行**；被護欄擋下的那一對，引擎只把它的混色排除、其餘五對照用（R6-4），
   而四料的「跨幅」看 48 格候選的**全域**跨幅（R6-7 附款 Q4）——紅×藍這種亮度相近的對天生跨幅小，
   逐對擋掉等於四料幾乎組不起來，也平白少掉彩度那條路（R6-11）。那一對會在第 1 步列成「⚠ 不會用到」。 */
function usable(mode, v){ return mode === 'quad' ? (v.kind === 'ok' || v.kind === 'blocked') : v.ok; }
function toggle(picked, key, need){
  const pk = (picked || []).slice(), i = pk.indexOf(key);
  if (i >= 0){ pk.splice(i, 1); return pk; }
  if (pk.length >= need) return [key];
  pk.push(key);
  return pk;
}

/* R6-16 允許留下的那一小塊自動配色：**只在已選的料裡決定哪支放哪一槽**，不發明顏色。
   只動一件事：最淺的那支放擠出機 1——循環洗料塔最後用擠出機 1 把噴頭洗乾淨、四料欄位直接寫「白色（料1）」，
   0919 Eric 確認機上 E1＝白（牌 c-0919-UI-02）。**其餘照給進來的順序**（人點的順序；從校正流程帶過來的＝校正當下的擠出機順序）：
   全部照亮到暗重排會把校正時裝在擠出機 2 的料搬到 3——人照原本裝好的料去印，顏色就錯了，而畫面上只差兩個小色塊。 */
function assignSlots(mats){
  if (mats.length < 2) return mats.slice();
  let top = 0, best = -Infinity;
  mats.forEach((m, i) => { const L = E().hexLstar(m.hex); if (L > best){ best = L; top = i; } });
  return [mats[top]].concat(mats.filter((_, i) => i !== top));
}

/* 一組已選齊的料 → 槽位、料色、色階上限、量測日期。回 null＝這組不成立（例如選好之後庫被改過）。 */
function setInfo(lib, mode, keys){ return setCheck(lib, mode, keys).info; }
/* 同上，但不成立時講得出為什麼（第 1 步點齊最後一支卻不成立時要講：FBK-11）。 */
function setCheck(lib, mode, keys){
  const need = NEED[mode] || 2;
  const byKey = new Map(M().listMaterials(lib).map(m => [m.key, m]));
  const ms = (keys || []).map(k => byKey.get(k));
  if (ms.length !== need || ms.some(x => !x)) return { info: null, why: '還沒選齊' };
  const mats = assignSlots(ms);
  const pairs = [], warn = [];
  for (let i = 0; i < mats.length; i++) for (let j = i + 1; j < mats.length; j++){
    const v = pairVerdict(lib, mats[i], mats[j]);
    const nm = mats[i].label + '×' + mats[j].label;
    if (!usable(mode, v)) return { info: null, why: nm + (v.kind === 'missing' ? '沒有一起校正過' : '：' + v.why) };
    pairs.push(v);
    if (!v.ok) warn.push(nm + '：' + v.why + '（這一對的混色不會用到）');
    else if (v.warn) warn.push(nm + '：' + v.warn);
  }
  let cap, span, colors;
  if (mode === 'dual'){
    /* 料色取**這一對**量到的兩端（同一支料在不同對裡量到的色不一樣；拿別對的色，引擎比料色會對不上＝整段不套用）。 */
    const t = M().toDualCalibTable(lib, mats[0], mats[1]).table;
    colors = t['料'].map(x => x['色']);
    span = pairs[0].span; cap = pairs[0].maxLevels;
  } else {
    const t = M().toQuadCalibTable(lib, mats).table;
    colors = mats.map(m => m.hex);
    const qc = E().quadCandidates(colors.map(c => ({ color: c })), LEVELS_MAX, { table: t, apply: true, toneMap: 'none' });
    span = qc.cands.length ? qc.Lmax - qc.Lmin : 0;           // R6-7 附款 Q4：48 格候選的全域跨幅
    cap = Math.min(LEVELS_MAX, Math.max(0, Math.floor(span)));
    if (!qc.plan || !qc.plan.applied) return { info: null, why: '這組料六對的量測都不能用' };
    if (span < 4) return { info: null, why: '這組料的實測亮度只差 ' + span.toFixed(1) + '，連 4 階都做不出來' };
  }
  /* 收起時寫「9/14 量的」：一組裡最近的那次量測（四料六對可能不同天量）。 */
  const at = pairs.map(v => v.pair.measuredAt || '').sort().pop() || null;
  return { info: { mode, keys: mats.map(m => m.key), mats, colors, pairs, span, cap, warn: warn.join('；'), at }, why: '' };
}

/* 庫裡所有成立的組（選齊、每一對都能用）。預設選擇用：上次選的那組不在了，就用最近量的那組。 */
function validSets(lib, mode){
  const need = NEED[mode] || 2, mats = M().listMaterials(lib);
  const okId = new Set();
  for (const p of (lib && lib.pairs) || []) if (usable(mode, pairVerdict(lib, p.a, p.b))) okId.add(p.id);
  const out = [];
  const rec = (start, cur) => {
    if (out.length >= 200) return;
    if (cur.length === need){
      const inf = setInfo(lib, mode, cur.map(m => m.key));
      if (inf) out.push({ keys: inf.keys, at: inf.pairs.map(v => v.pair.measuredAt || '').sort().pop() });
      return;
    }
    for (let i = start; i < mats.length; i++)
      if (cur.every(q => okId.has(M().pairId(q, mats[i])))){ cur.push(mats[i]); rec(i + 1, cur); cur.pop(); }
  };
  rec(0, []);
  return out;
}
function defaultKeys(lib, mode, remembered){
  if (remembered && remembered.length && setInfo(lib, mode, remembered)) return remembered.slice();
  const sets = validSets(lib, mode);
  if (!sets.length) return [];
  let best = sets[0];
  sets.forEach(s => { if ((s.at || '') >= (best.at || '')) best = s; });   // 同日期取庫裡較後面的＝較晚收進來的
  return best.keys;
}

/* 產圖時掛進 request.slots[0].calib 的那一份（形狀與雙料 0914 那支 calibRequest 逐字同：table／apply／toneMap）。 */
function calibRequestFor(lib, info, params){
  if (!info) return null;
  const table = info.mode === 'dual' ? M().toDualCalibTable(lib, info.mats[0], info.mats[1]).table
                                     : M().toQuadCalibTable(lib, info.mats).table;
  if (!table) return null;
  const apply = !!(params && params.calibGen);
  return { table, apply, toneMap: (apply && params.calibStretch) ? 'stretch' : 'none' };
}

/* Q1（Eric 2026-09-23 裁「照建議」；R6-15）：AI 產圖前把「這組料印得出的顏色」寫進提示詞尾端。
   接在調性鐵則（toneRules）**後面**：toneRules 自己寫「與上面的配色指示衝突時以上面為準」，
   放在它上面會被它讓位；放在它下面才管得到款式模板裡寫死的那組參考色（R9-10 在選色這關已被 R6-16 取代）。 */
function aiPaletteLine(info){
  if (!info || !Array.isArray(info.colors) || !info.colors.length) return '';
  const hex = info.colors.map(h => String(h).toUpperCase());
  return 'PRINTABLE PALETTE (this overrides any colour or palette named above): the tile is printed with exactly '
    + hex.length + ' filament colours — ' + hex.join(', ') + '. Use ONLY these colours, or a mix of any two of them '
    + '(a step between two of these colours). Do not introduce any other hue.';
}

/* ---- 「指定材料」元件的純邏輯（T061；node 測得到）---- */
const TYPES_FALLBACK = ['PLA'];
/* 料種清單＝App 從切片參數給（capability 的 materialTypes：照片磚印得出來的料種，〈九〉Q1 甲）。
   瀏覽器直開（開發）讀不到參數庫 ⇒ 退回只列 PLA（今天照片磚也只有 PLA；〈九〉9-3）。 */
function typeList(list){
  const t = (Array.isArray(list) ? list : []).map(x => String(x == null ? '' : x).trim()).filter(Boolean);
  return t.length ? Array.from(new Set(t)) : TYPES_FALLBACK.slice();
}
/* 庫裡這個料種用過的顏色名（下拉提示用；只算已指定料種的料）。 */
function namesOf(lb, type){
  const out = [];
  M().listMaterials(lb).forEach(m => { if (m.type === type && out.indexOf(m.label) < 0) out.push(m.label); });
  return out;
}
/* 名字提示（Eric 2026-09-23 看原型裁：「這邊名字是我任意取的，所以不需要阻擋。你只要提示是否重複了，
   如果我沒有選擇它的話，那它就是一隻新的材料」）⇒ 只講事實、不擋：
   same＝庫裡一字不差＝同一支料；near＝互相包含的相近名字（最多 3 個，給他點）；都沒有＝new（新的一支）。 */
function nameHint(lb, type, name){
  name = String(name == null ? '' : name).trim();
  if (!name) return { kind: '', name: '', near: [] };
  const names = namesOf(lb, type);
  if (names.indexOf(name) >= 0) return { kind: 'same', name, near: [] };
  const near = names.filter(n => n.indexOf(name) >= 0 || name.indexOf(n) >= 0)
    .sort((a, b) => Math.abs(a.length - name.length) - Math.abs(b.length - name.length)).slice(0, 3);
  return { kind: near.length ? 'near' : 'new', name, near };
}
/* 同一組裡兩支同料種同名＝拿一支料跟自己校正——唯一擋的情形。回撞到的那兩個索引，沒撞回 null。 */
function dupIn(rows){
  const xs = (rows || []).map(r => ({ type: r && r.type, label: String((r && r.label) || '').trim() }));
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++)
    if (xs[i].label && xs[i].label === xs[j].label && xs[i].type === xs[j].type) return [i, j];
  return null;
}
/* 庫裡同一支料（料種＋顏色名一字不差）＝校正第 1 步的色塊帶出「上次量到的顏色」、校正片的名目色。 */
function knownMat(lb, type, name){
  name = String(name == null ? '' : name).trim();
  if (!type || !name) return null;
  const k = M().matKey({ type, label: name });
  return M().listMaterials(lb).find(m => m.key === k) || null;
}
function mdate(d){ const m = /^\d{4}-(\d{2})-(\d{2})/.exec(d || ''); return m ? (+m[1]) + '/' + (+m[2]) : ''; }
/* 校正表本身沒記日期；常見檔名是 20260914_雙料_白x深灰_….json ⇒ 從檔名抓，抓不到＝null（收下時用今天）。
   為什麼要：同一組新的取代舊的、畫面寫「9/14 量的」，日期錯了這兩件都錯。 */
function dateFromName(fn){
  const m = /(20\d{2})(\d{2})(\d{2})/.exec(String(fn || ''));
  if (!m || +m[2] < 1 || +m[2] > 12 || +m[3] < 1 || +m[3] > 31) return null;
  return m[1] + '-' + m[2] + '-' + m[3];
}

/* ================= 畫面（只在瀏覽器） ================= */

let page = null;              // index.html 交進來的轉接物件（見 mount）
let flow = 'gen';             // gen＝產圖流程｜cal＝校正流程
let open = false;             // 使用者自己打開（按「換一組…」）。還沒有可用的那組時，不論這個旗標都是展開的——
                              // 🔴 兩件事不能混成一個旗標：App 的庫是非同步讀回來的，讀回來自動選好一組之後要自己收起（段 F 截圖抓到）
let draft = null;             // 展開時正在點的那組（選齊才生效；沒選齊就收起＝維持原本那組）
let flash = null;             // 這一塊的一行訊息 {kind:'warn'|'ok', text, cal:附「去校正一組料」}
const applied = { dual: null, quad: null };   // 生效中的那組（setInfo 的結果）
let remembered = { dual: [], quad: [] };
let calStep = 1, calIds = null, calDoneInfo = null, calErr = '', calMiss = [];
let importFrom = 'cal';       // 這次匯入校正表是從哪裡按的：gen＝右欄料單（收下後留在產圖流程）｜cal＝校正第 4 步
let genAccepting = false;     // 右欄匯入「放進材料庫」那一下（同步呼叫 acceptTable 期間）——onCalibrated 據此留在產圖流程講結果。
                              // 🔴 不拿 importFrom 判：開檔視窗按取消不會有任何事件，旗標會一直停在 gen，之後校正流程收表就走錯路

function loadRemembered(){
  try { const s = JSON.parse(root.localStorage.getItem(SEL_KEY) || 'null');
        if (s && typeof s === 'object') return { dual: Array.isArray(s.dual) ? s.dual : [], quad: Array.isArray(s.quad) ? s.quad : [] }; }
  catch (e) {}
  return { dual: [], quad: [] };
}
function saveRemembered(){ try { root.localStorage.setItem(SEL_KEY, JSON.stringify(remembered)); } catch (e) {} }
function $(id){ return root.document.getElementById(id); }
function mode(){ return page ? page.mode() : 'dual'; }
function lib(){ return (page && page.lib()) || M().emptyLib(); }
function types(){ return typeList(page && page.materialTypes ? page.materialTypes() : null); }
function save(){ if (page && page.save) page.save(); }
/* 🔴 本地日期：toISOString() 是 UTC——台灣早上 8 點前會記成前一天（瀏覽器實走抓到：9/24 早上記成 9/23），
   畫面上的「9/23 量的」就錯一天、新舊版本的先後也跟著錯。 */
function today(){ const t = new Date(); return new Date(t.getTime() - t.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
function whenText(d){ const m = mdate(d); return m ? m + ' 量的' : '舊表、沒記日期'; }

/* 目前這個料數（或指定料數）生效中的那組；庫變了（指定料種、重量測）就重算，不成立就退回預設。 */
function current(which){
  const md = NEED[which] ? which : mode();
  const a = applied[md];
  if (a){ const again = setInfo(lib(), md, a.keys); if (again){ applied[md] = again; return again; } }
  const keys = defaultKeys(lib(), md, remembered[md]);
  applied[md] = keys.length ? setInfo(lib(), md, keys) : null;
  return applied[md];
}
function ready(){ return !!current(); }
function info(md){ return current(md); }
/* 「產生」被擋、或款式／AI 需要先選料時的出口（FBK-11：訊息叫人去哪裡，就給他一顆過去的按鈕）。 */
function openPicker(){ if (flow !== 'gen') setFlow('gen'); open = true; draft = null; flash = null; renderPanel(); scrollPanel(); }
function calibRequest(){ return calibRequestFor(lib(), current(), page && page.params()); }

function useKeys(md, keys){
  const inf = setInfo(lib(), md, keys);
  if (!inf) return false;
  applied[md] = inf; remembered[md] = inf.keys.slice(); saveRemembered();
  return true;
}
/* 指定料種＝身分換了、鍵跟著換 ⇒ 生效中的那組、記住的那組一起換（否則指定完原本那組就「選不到」了）。 */
function remapKeys(renamed){
  ['dual', 'quad'].forEach(md => {
    if (applied[md]) applied[md].keys = applied[md].keys.map(k => renamed.get(k) || k);
    remembered[md] = remembered[md].map(k => renamed.get(k) || k);
  });
  saveRemembered();
}

/* ---- 右欄「選顏色」這一塊 ---- */
function flashHtml(){
  if (!flash) return '';
  return '<div class="mfFlash ' + (flash.kind === 'ok' ? 'ok' : 'warn') + '">' + esc(flash.text)
    + (flash.cal ? '<button type="button" class="btn ghost" data-mf="tocal">去校正一組料</button>' : '') + '</div>';
}
/* 料單上的名字：已指定＝顏色名＋料種小標；舊資料＝原本的標籤＋「未指定料種」＋「指定…」（Q12 跳過之後隨時補）。 */
function nameCell(m){
  return M().needsSpec(m)
    ? '<span class="mfNm">' + esc(m.label) + '</span><span class="mfTagW">未指定料種</span>'
      + '<button type="button" class="btn ghost mfXs" data-mf="spec" data-k="' + esc(m.key) + '">指定…</button>'
    : '<span class="mfNm">' + esc(m.label) + '</span><span class="mfTagT">' + esc(m.type) + '</span>';
}
function renderPanel(){
  const box = $('matPanel'); if (!box) return;
  const md = mode(), need = NEED[md], lb = lib(), inf = current();
  const mats = M().listMaterials(lb);
  const note = page && page.note ? page.note() : '';
  const noteHtml = note ? '<div class="sub warn">⚠ ' + esc(note) + '</div>' : '';
  const head = t => '<div class="mfH">選顏色' + (t || '') + '</div>';
  if (!mats.length && page && page.loading && page.loading()){
    /* App 那一份是非同步讀回來的：讀回來之前庫是空的，但那不是「你沒有校正過」——講實話，不先嚇人。 */
    box.innerHTML = head() + '<div class="sub">正在讀取材料庫…</div>';
    return;
  }
  if (!mats.length){
    box.innerHTML = head() + '<div class="mfEmpty"><b>還沒有校正過的顏色。</b><br>沒量過的料，系統不知道它印出來是什麼顏色，所以這裡選不到。'
      + '先校正一組料（印一片校正片、拍一張照），它就會出現在這裡。'
      + '<div class="mfActs"><button type="button" class="btn primary" data-mf="tocal">去校正一組料</button>'
      + '<button type="button" class="btn ghost" data-mf="import">匯入校正表…</button></div></div>' + flashHtml() + noteHtml;
    return;
  }
  if (!open && inf){
    /* Eric 2026-09-23 看原型：「在還沒有按下『換一組』之前，那個『1』顏色顯得怪怪的，刪除它，直到按下『換一組』的時候，再出現下方的步驟。」
       ⇒ 收起時不放步驟號與標題，只寫「擠出機幾號裝什麼」＋「換一組…」（Eric 0919：「這樣我也知道擠出機 1 跟擠出機 2 我要放什麼料」）；
       擠出機顏色只寫這一處（列印模擬標題列的色塊已拿掉：「資訊好像重疊了，是否留一個就好了呢？」）。
       說明那一行「平時安靜、異常才出聲」：上限被壓低、資料有疑慮、校正值沒套用、存不進去才多講。
       ⛔ 列印內容用的不是實測值時一定要看得到（R8-5「摘要行不准只講好消息」）——狀態文字由頁面依這次模擬的結果寫。 */
    const st = page && page.statusLine ? page.statusLine() : '';
    box.innerHTML = '<div class="mfTop"><div class="mfExts">' + inf.mats.map((m, i) =>
        '<span class="mfExt"><span class="k">擠出機 ' + (i + 1) + '</span><span class="mfSw" style="background:' + esc(inf.colors[i]) + '"></span>'
        + '<span class="v" title="' + esc(m.type ? m.type + ' ' + m.label : m.label) + '">' + esc(m.label) + '</span></span>').join('')
      + '</div><button type="button" class="btn ghost" data-mf="open">換一組…</button></div>'
      + '<div class="mfMeta">最多 ' + inf.cap + ' 階・' + whenText(inf.at) + '</div>'
      + (inf.cap < LEVELS_MAX ? capLine(inf) : '')
      + '<div class="sub warn" id="mfStatus">' + esc(st) + '</div>'
      + (inf.warn ? '<div class="sub warn">⚠ 資料有疑慮但不擋：' + esc(inf.warn) + '</div>' : '')
      + flashHtml() + noteHtml;
    return;
  }
  const d = draft && draft.mode === md ? draft.picked : (inf ? inf.keys.slice() : []);
  const ch = choices(lb, md, d);
  /* Eric 2026-09-23 看原型的三則疊在一起才是這個長相：①「材料的匯入匯出，應該在材料那一個區塊的右上方進行控制」
     ②「我今天想要更換材料，就只有第一個『換一組』，這是第一步。所以第二步是去選擇材料，或是沒有材料的時候要去校正。
        因此選擇材料跟校正其實是平行的，它沒有先後順序」③「校正跟匯入是不是同一組？也就是對於下面的清單會增加或者修正」
     ⇒ 往清單加料／更新的兩條路（校正、匯入）併成一組放料單右上；標題列只剩標題＋收起；不掛步驟號；
       原本最底下「沒有想要的顏色？」那一行拿掉（跟選料平行的入口已經在上面）。匯出與已封存＝T062。 */
  let h = head('<span class="hint">' + (md === 'dual' ? '雙料，挑 2 支' : '四料，挑 4 支') + '</span><span class="mfSp"></span>'
        + (inf ? '<button type="button" class="btn ghost" data-mf="close">收起</button>' : ''))
        + '<div class="sub">清單只有校正過的料——沒量過的料，系統不知道它印出來是什麼顏色，所以選不到。</div>'
        + '<div class="mfLibBar"><span class="mfLibT">材料庫</span><span class="sub">新增或更新：</span>'
        + '<button type="button" class="btn ghost" data-mf="tocal">去校正一組料</button>'
        + '<button type="button" class="btn ghost" data-mf="import">匯入校正表…</button></div>'
        + '<table class="mfTable"><thead><tr><th>選</th><th>材料</th><th>料色</th></tr></thead><tbody>';
  ch.rows.forEach(r => {
    const m = r.mat;
    h += '<tr class="mfRow ' + r.state + '" data-key="' + esc(m.key) + '">'
       + '<td><span class="mfPick' + (r.state === 'picked' ? ' on' : '') + '">' + (r.state === 'picked' ? (r.order + 1) : (r.state === 'no' ? '🔒' : '')) + '</span></td>'
       + '<td>' + nameCell(m) + (r.state === 'no' ? '<div class="mfWhy">' + esc(r.why) + '</div>' : '') + '</td>'
       + '<td><span class="mfSw" style="background:' + esc(m.hex) + '"></span> <code>' + esc(m.hex) + '</code></td></tr>';
  });
  h += '</tbody></table>';
  const miss = need - ch.picked.length;
  h += '<div class="sub mfNow">' + (ch.picked.length ? '已點：' + ch.picked.map(k => esc((ch.rows.find(r => r.mat.key === k) || {}).mat.label)).join('、') : '還沒點')
     + (miss > 0 ? '（還缺 ' + miss + ' 支；選齊就生效——最淺的那支自動放擠出機 1，其餘照你點的順序）' : '') + '</div>';
  box.innerHTML = h + flashHtml() + noteHtml;
}
function capLine(inf){
  if (!inf) return '';
  const span = Number(inf.span || 0).toFixed(1);
  return '<div class="sub">這組料最多做得出 <b>' + inf.cap + ' 階</b>（實測亮度跨幅 ' + span + '，每階至少要跨過 1 個人眼分得出的單位）'
       + (inf.cap < LEVELS_MAX ? '——色階數上限已經壓到這裡。' : '。') + '</div>';
}

function onPanelClick(e){
  const t = e.target.closest ? e.target.closest('[data-mf],[data-key]') : null;
  if (!t) return;
  const act = t.getAttribute('data-mf');
  if (act === 'open'){ open = true; draft = null; flash = null; renderPanel(); scrollPanel(); return; }
  if (act === 'close'){ open = false; draft = null; flash = null; renderPanel(); return; }
  if (act === 'tocal'){ flash = null; setFlow('cal'); return; }
  if (act === 'import'){ pickTableFile(); return; }
  if (act === 'spec'){ openSpecOne(t.getAttribute('data-k')); return; }
  const key = t.getAttribute('data-key');
  if (!key) return;
  const md = mode(), inf = current();
  const base = draft && draft.mode === md ? draft.picked : (inf ? inf.keys.slice() : []);
  const ch = choices(lib(), md, base);
  const row = ch.rows.find(r => r.mat.key === key);
  if (!row) return;
  if (row.state === 'no'){ flash = { kind: 'warn', text: '「' + row.mat.label + '」選不到：' + row.why + '。要用它，先把這組料一起校正。', cal: true }; renderPanel(); return; }
  flash = null;
  const next = toggle(ch.picked, key, ch.need);
  draft = { mode: md, picked: next };
  if (next.length === ch.need){
    const chk = setCheck(lib(), md, next);
    if (chk.info && useKeys(md, next)){ open = false; draft = null; changed(); return; }
    flash = { kind: 'warn', text: '這組選不起來：' + chk.why + '。' };
  }
  renderPanel();
}
function scrollPanel(){ const b = $('matPanel'); if (b && b.scrollIntoView) b.scrollIntoView({ block: 'nearest' }); }

/* 選的那組變了 ⇒ 交回頁面（寫料槽、壓色階上限、重算）。只在真的變了才交：頁面收到之後會重畫料槽、
   又呼叫回 refresh()——用簽章擋住，不會繞圈。庫讀回來（App 是非同步）、收下新表、指定料種，都走這一支。 */
let lastSig = null;
function sigOf(inf){ return inf ? [inf.mode, inf.keys.join(','), inf.colors.join(','), inf.cap].join('|') : mode() + '|none'; }
function notify(force){
  const inf = current(), s = sigOf(inf);
  if (!force && s === lastSig) return;
  lastSig = s;
  if (page) page.applied(inf);
}
function changed(){
  renderPanel();
  notify();
}

/* ---- 「指定材料」元件（〈九〉Q5：校正第 1 步／匯入校正表之後／舊資料第一次開，三處同一個長相）----
   o：{ i, k（舊資料的鍵）, title, titleSub, hex（量到的色；null＝還沒量）, type, name, sub, miss } */
function mpHtml(o){
  const T = types();
  const type = T.indexOf(o.type) >= 0 ? o.type : T[0];
  const known = !o.hex && o.name ? knownMat(lib(), type, o.name) : null;
  const hex = o.hex || (known ? known.hex : null);
  return '<div class="mp' + (o.miss ? ' miss' : '') + '" data-i="' + o.i + '"' + (o.k ? ' data-k="' + esc(o.k) + '"' : '')
    + (o.hex ? ' data-hex="' + esc(o.hex) + '"' : '') + '>'
    + '<div class="mpT">' + esc(o.title) + (o.titleSub ? '<span class="sub">' + esc(o.titleSub) + '</span>' : '') + '</div>'
    + '<div class="mpRow"><span class="mpSw' + (hex ? '' : ' none') + '"' + (hex ? ' style="background:' + esc(hex) + '"' : '') + '></span>'
    + '<label>料種 <select data-f="type">' + T.map(t => '<option' + (t === type ? ' selected' : '') + '>' + esc(t) + '</option>').join('') + '</select></label>'
    + '<label>顏色名 <input type="text" data-f="name" list="mfNames' + T.indexOf(type) + '" value="' + esc(o.name || '') + '" placeholder="例：白、深灰" autocomplete="off"></label></div>'
    + '<div class="mpSub">' + swCaption(o.hex, known) + (o.sub ? '<br>' + esc(o.sub) : '') + '</div>'
    + '<div class="mpHint">' + hintHtml(type, o.name, '') + '</div></div>';
}
/* 色塊只放量到的色（〈九〉原型細節 8：「不拿擠出機設定色充數」——T060 的白×黑就是這樣來的）。 */
function swCaption(hex, known){
  if (hex) return '色塊＝量到的 <code>' + esc(hex) + '</code>（自動帶入，只當紀錄）';
  if (known) return '色塊＝「' + esc(known.label) + '」上次量到的 <code>' + esc(known.hex) + '</code>（這次量完換成新的）';
  return '色塊量完自動帶入';
}
function hintHtml(type, name, dupWith){
  const h = nameHint(lib(), type, name);
  if (!h.kind) return '';
  if (dupWith) return '<div class="mpInfo">跟' + esc(dupWith) + '同名＝會當成同一支料。</div>';
  if (h.kind === 'same') return '<div class="mpInfo">＝庫裡已有的「' + esc(h.name) + '」（同一支料）。</div>';
  if (h.kind === 'near') return '<div class="mpInfo">新的一支料「' + esc(h.name) + '」。庫裡有相近的：'
    + h.near.map(n => '<button type="button" class="nmChip" data-use="' + esc(n) + '">' + esc(n) + '</button>').join('')
    + '——是同一支就點它，不點就當新的。</div>';
  return '<div class="mpInfo">新的一支料「' + esc(h.name) + '」。</div>';
}
/* 下拉提示：每個料種一份 datalist（庫裡這個料種用過的名字）。擋「白」「白色」分裂的做法是提示、不是擋（Q8＋9-6①）。 */
function renderNames(){
  const doc = root.document; if (!doc) return;
  let host = $('mfNameLists');
  if (!host){ host = doc.createElement('div'); host.id = 'mfNameLists'; host.hidden = true; doc.body.appendChild(host); }
  host.innerHTML = types().map((t, i) => '<datalist id="mfNames' + i + '">'
    + namesOf(lib(), t).map(n => '<option value="' + esc(n) + '">').join('') + '</datalist>').join('');
}
function mpRead(box){
  return Array.prototype.map.call(box.querySelectorAll('.mp'), el => ({ el, i: +el.getAttribute('data-i'), k: el.getAttribute('data-k'),
    type: el.querySelector('[data-f=type]').value, name: el.querySelector('[data-f=name]').value.trim() }));
}
/* 打字就重畫提示；同一組裡撞名要講（唯一擋的情形在確認那一下擋，這裡先提示）。 */
function mpRefresh(box){
  const rows = mpRead(box);
  rows.forEach((r, j) => {
    const other = r.name ? rows.find((o, k) => k !== j && o.name === r.name && o.type === r.type) : null;
    r.el.querySelector('.mpHint').innerHTML = hintHtml(r.type, r.name, other ? '「' + other.el.querySelector('.mpT').firstChild.textContent + '」' : '');
    r.el.querySelector('[data-f=name]').setAttribute('list', 'mfNames' + types().indexOf(r.type));
    if (r.name) r.el.classList.remove('miss');
    if (!r.el.hasAttribute('data-hex')){
      const known = knownMat(lib(), r.type, r.name), s = r.el.querySelector('.mpSw');
      s.classList.toggle('none', !known); s.style.background = known ? known.hex : '';
      r.el.querySelector('.mpSub').innerHTML = swCaption(null, known);
    }
  });
}
function useName(btn){
  const mp = btn.closest('.mp'), inp = mp && mp.querySelector('[data-f=name]');
  if (!inp) return;
  inp.value = btn.getAttribute('data-use');
  inp.dispatchEvent(new root.Event('input', { bubbles: true }));
  inp.focus();
}

/* ---- 頁內對話框（FBK-19：嵌入式 WebView 一律頁內窗；FBK-10：點背景不關；LAY-15：肯定在左、取消恆在最右）---- */
let dlg = null;
function openDlg(o){
  closeDlg();
  const doc = root.document;
  const back = doc.createElement('div'); back.className = 'cfmBack';
  back.innerHTML = '<div class="cfmBox mfDlg" role="dialog" aria-modal="true" tabindex="-1">'
    + '<div class="cfmTitle">' + esc(o.title) + '</div><div class="cfmBody">' + o.body + '</div><div class="mfDlgErr"></div>'
    + '<div class="cfmBtns">' + o.buttons.map(b => '<button type="button" class="btn' + (b.primary ? ' primary' : '') + '" data-c="' + b.c + '">'
      + esc(b.label) + '</button>').join('') + '</div></div>';
  doc.body.appendChild(back);
  dlg = { back, o };
  back.addEventListener('click', ev => {
    const u = ev.target.closest && ev.target.closest('[data-use]');
    if (u){ useName(u); return; }
    const b = ev.target.closest && ev.target.closest('[data-c]');
    if (b && o.on(b.getAttribute('data-c'), back) !== false) closeDlg();
  });
  const upd = ev => { if (ev.target.matches && ev.target.matches('[data-f]')) mpRefresh(back); };
  back.addEventListener('input', upd); back.addEventListener('change', upd);
  renderNames();
  const first = back.querySelector('[data-f=name]');
  (first || back.querySelector('.cfmBox')).focus();
}
function closeDlg(){ if (dlg){ const d = dlg; dlg = null; d.back.remove(); } }
function dlgErr(box, text){ const e = box.querySelector('.mfDlgErr'); if (e) e.textContent = text; }
/* 名字都要填、同一組不能撞名。 */
function mpCheck(box, rows){
  const miss = rows.filter(r => !r.name);
  rows.forEach(r => r.el.classList.toggle('miss', !r.name));
  if (miss.length){ dlgErr(box, '請先補上顏色名（已標出來）。'); miss[0].el.querySelector('[data-f=name]').focus(); return false; }
  const dup = dupIn(rows.map(r => ({ type: r.type, label: r.name })));
  if (dup){ dlgErr(box, '兩支都叫「' + rows[dup[0]].name + '」，系統會當成同一支料——請改成認得出來的名字（例：白、深灰）。'); return false; }
  return true;
}

/* ---- 匯入校正表（〈九〉Q5：匯入不再跳過確認）----
   T060 的「匯入校正表…」會跳過校正第 1 步，料的身分取自擠出機目前的線材設定——Eric 看到「白×黑」就是這樣來的（〈九〉起因②）。
   ⇒ 一律先問「這張表是哪幾支料」（同一個「指定材料」元件，色塊＝表上量到的色、表上寫的名字只當提示），確認才收。
   從校正第 4 步匯入＝剛量的那組：先帶第 1 步填的名字，確認一次就好。 */
function pickTableFile(){
  let f = $('mfTableFile');
  if (!f){
    f = root.document.createElement('input'); f.type = 'file'; f.id = 'mfTableFile'; f.accept = '.json,application/json'; f.hidden = true;
    f.addEventListener('change', () => {
      const file = f.files && f.files[0]; f.value = '';
      if (!file) return;
      const rd = new root.FileReader();
      rd.onload = () => { let raw; try { raw = JSON.parse(rd.result); } catch (e) { importFrom = 'gen'; importFail('這個檔匯不進來：不是合法的 JSON。'); return; }
                          importTable(raw, file.name, 'gen'); };
      rd.readAsText(file);
    });
    root.document.body.appendChild(f);
  }
  f.click();
}
function importFail(text){
  if (importFrom === 'gen'){ flash = { kind: 'warn', text }; renderPanel(); }
  else { const el = $('calibTableStat'); if (el) el.textContent = '⚠ ' + text; }
  importFrom = 'cal';
}
function importTable(raw, fname, from){
  importFrom = from === 'gen' ? 'gen' : 'cal';
  let tbl;
  try { tbl = E().calibParseTable(raw); }
  catch (e){ importFail('這個檔匯不進來：' + ((e && e.message) || '不是校正表') + '。'); return; }
  const quad = Array.isArray(tbl.pairs), n = quad ? 4 : 2;
  const decl = (raw && Array.isArray(raw['料']) ? raw['料'] : []).map(x => String((x && x['名']) || '').trim());
  const at = dateFromName(fname);
  const pre = importFrom === 'cal' && calIds && calIds.length === n && calIds.every(x => String(x.label || '').trim()) ? calIds : null;
  openDlg({ title: '這張校正表是哪' + (quad ? '四' : '兩') + '支料？',
    body: '<div class="mfDetect">✓ 認出來了：這是一張<b>校正表</b>（' + (quad ? '四料 48 格' : '雙料') + (at ? '，檔名上的日期 ' + mdate(at) : '') + '）。</div>'
      + '<p>告訴我料種跟顏色名就好；顏色是量到的，已經自動帶進來。' + (pre ? '先帶了校正第 1 步填的名字，對了就按「放進材料庫」。' : '') + '</p>'
      + tbl.slots.slice(0, n).map((hex, i) => mpHtml({ i, title: '第 ' + (i + 1) + ' 支（擠出機 ' + (i + 1) + '）',
          titleSub: decl[i] && !/^#?[0-9A-F]{6}$/i.test(decl[i]) ? '表上寫的是「' + decl[i] + '」' : '',
          hex, type: pre ? pre[i].type : types()[0], name: pre ? pre[i].label : '' })).join(''),
    buttons: [{ c: 'yes', label: '放進材料庫', primary: true }, { c: 'no', label: '取消' }], esc: 'no',
    on(c, box){
      if (c !== 'yes'){ importFrom = 'cal'; return true; }
      const rows = mpRead(box);
      if (!mpCheck(box, rows)) return false;
      genAccepting = importFrom === 'gen';
      let r = null;
      try { r = page && page.acceptTable ? page.acceptTable(raw, rows.map(x => ({ type: x.type, label: x.name })), at) : null; }
      finally { genAccepting = false; }
      if (!r || !r.added) importFail('沒放進材料庫：' + ((r && r.why) || '材料庫未載入') + '。');
      else importFrom = 'cal';
      return true;
    } });
}

/* ---- 舊資料第一次開時問一次（R6-14 子題 2 附款的附款＝〈九〉Q12「照建議」；取代「第一次在產圖流程選到時認領」）----
   舊版存的料只記了色號或線材名、沒有料種 ⇒ 開新版時用同一個「指定材料」元件一次問完。問過就記在庫（legacyAskedAt），
   跳過的料清單上標「未指定料種」、旁邊「指定…」隨時補——**不會每次開都再問**。
   ⚙ 原型那一問每支旁邊還有「封存」＝T062（封存還沒做）；本版改成**空著＝先不指定**（講在窗裡），不逼人亂填。
   兩支舊料指到同一支料＝合成一支；同一組量過兩次＝新的當目前、舊的留一份（matlib.specifyMaterials）。 */
function declName(m){
  /* 舊鍵那張表遷進來時標籤是色號，但表上原本寫了名字（例：第二支寫「紅」）——給人認得出是哪一張。只讀、不改。 */
  const raw = M().readLegacyRaw();
  const hit = (raw && Array.isArray(raw['料']) ? raw['料'] : []).find(x => x && String(x['色'] || '').toUpperCase() === m.hex);
  const nm = hit ? String(hit['名'] || '').trim() : '';
  return nm && nm !== m.label ? '表上寫的是「' + nm + '」' : '';
}
function partnerText(lb, m){
  const p = M().partnersOf(lb, m)[0];
  return p ? whenText(p.pair.measuredAt) + '，和「' + p.other.label + '」一組' : '';
}
/* 🔴 別的對話框開著時要等它關掉——但它關掉的那一刻沒有任何事件通知這裡（瀏覽器實走抓到：開圖時的「主角是？」
   把這一問擋掉之後就再也沒出現），而頁面的對話框程式還會把 .cfmBack **全部**拿掉（連這一問一起）。
   ⇒ 只在「還有舊資料沒問」的期間每秒看一次：被擋就等、被拿掉就重開；問過（legacyAskedAt）或沒有舊資料就停。 */
let askTimer = null;
function askLater(){ if (!askTimer) askTimer = root.setTimeout(() => { askTimer = null; maybeAskLegacy(); }, 1000); }
function maybeAskLegacy(){
  if (dlg && !dlg.back.isConnected) dlg = null;      // 頁面別的對話框會把 .cfmBack 全部拿掉——被拿掉就當這次沒問、等下重開
  const doc = root.document, lb = lib();
  if (!doc || lb.legacyAskedAt) return;
  const leg = M().listMaterials(lb).filter(m => M().needsSpec(m));
  if (!leg.length) return;
  if (dlg){ if (dlg.o.legacy) askLater(); return; }  // 這一問開著：繼續看它有沒有被別人拿掉
  if (flow !== 'gen') return;                        // 在校正流程裡不問；回產圖流程時 setFlow 會再叫一次
  if (page && ((page.loading && page.loading()) || (page.typesReady && !page.typesReady()))) return;   // 庫與料種清單都到了才問（到的時候 refresh 會叫）
  if (doc.querySelector('.cfmBack')){ askLater(); return; }   // 別的對話框開著：不疊上去，等它關
  openDlg({ legacy: true, title: '舊版留下的校正資料——它們是什麼料？（只問這一次）',
    body: '<p>新版用「<b>料種＋顏色名</b>」認一支料（量到的色號只當紀錄）。下面這 ' + leg.length + ' 支是舊版存的，只記了色號或線材名。'
      + '<b>不確定的空著就好</b>——之後在清單上按「指定…」再補。</p>'
      + leg.map((m, i) => mpHtml({ i, k: m.key, title: m.label, titleSub: declName(m), hex: m.hex, type: types()[0], name: '',
          sub: partnerText(lb, m) })).join(''),
    buttons: [{ c: 'yes', label: '確定', primary: true }, { c: 'no', label: '先跳過' }], esc: 'no',
    on(c, box){
      if (c !== 'yes'){
        lb.legacyAskedAt = today(); save();
        open = true; flash = { kind: 'warn', text: '先跳過了。還沒指定料種的料在清單上標「未指定料種」，旁邊「指定…」隨時可以補；不會每次開都再問。' };
        renderPanel(); return true;
      }
      const rows = mpRead(box), filled = rows.filter(r => r.name);
      const map = new Map(filled.map(r => [r.k, { type: r.type, label: r.name }]));
      const conf = M().specifyConflicts(lb, map);
      if (conf.length){ dlgErr(box, '「' + conf[0].label + '」和同一組的另一支同名——同一組的兩支不能是同一支料。'); return false; }
      if (map.size) remapKeys(M().specifyMaterials(lb, map));
      lb.legacyAskedAt = today(); save();
      const left = rows.length - filled.length;
      if (left) open = true;
      flash = { kind: filled.length ? 'ok' : 'warn', text: (filled.length ? '舊資料整理好了：指定 ' + filled.length + ' 支。' : '都空著＝先跳過了。')
        + (left ? left + ' 支先不指定（清單上標「未指定料種」，旁邊「指定…」隨時補）。' : '') };
      renderPanel(); notify(); return true;
    } });
}
/* 清單上「指定…」（跳過之後補）：同一個元件，一支。 */
function openSpecOne(key){
  const lb = lib(), m = M().listMaterials(lb).find(x => x.key === key);
  if (!m) return;
  openDlg({ title: '這支是什麼料？',
    body: mpHtml({ i: 0, k: m.key, title: m.label, titleSub: declName(m), hex: m.hex, type: types()[0], name: '', sub: partnerText(lb, m) }),
    buttons: [{ c: 'yes', label: '確定', primary: true }, { c: 'no', label: '取消' }], esc: 'no',
    on(c, box){
      if (c !== 'yes') return true;
      const r = mpRead(box)[0];
      if (!r.name){ r.el.classList.add('miss'); dlgErr(box, '請先填顏色名（已標出來）。'); r.el.querySelector('[data-f=name]').focus(); return false; }
      const map = new Map([[m.key, { type: r.type, label: r.name }]]);
      if (M().specifyConflicts(lb, map).length){ dlgErr(box, '跟同一組的另一支同名——同一組的兩支不能是同一支料。'); return false; }
      remapKeys(M().specifyMaterials(lb, map)); save();
      flash = { kind: 'ok', text: '已指定：' + r.type + ' ' + r.name + '。' };
      renderPanel(); notify(); return true;
    } });
}

/* ---- 兩條流程的切換（原型 v3 右上那組切換）---- */
function setFlow(f){
  flow = f === 'cal' ? 'cal' : 'gen';
  const doc = root.document;
  doc.body.classList.toggle('flowCal', flow === 'cal');
  const seg = $('flowSeg');
  if (seg) Array.prototype.forEach.call(seg.children, b => b.classList.toggle('on', b.getAttribute('data-flow') === flow));
  const cal = $('calFlow'); if (cal) cal.hidden = flow !== 'cal';
  if (flow === 'cal'){ if (!calIds || calIds.length !== NEED[mode()]) calIds = defaultCalIds(); renderCal(); }
  else { open = false; renderPanel(); notify(); maybeAskLegacy(); }
}

/* ---- 校正流程 ---- */
/* 第 1 步「放一組料」＝「指定材料」元件（料種＋顏色名）；名字**不預設**（〈九〉Q8「不預設色號」）。
   🔴 身分由人確認，**不從校正片去猜哪一端是哪一支**（段 B 的界線）。 */
function defaultCalIds(){
  const n = NEED[mode()], t = types()[0];
  return Array.from({ length: n }, () => ({ type: t, label: '' }));
}
function ensureCal(){ if (!calIds || calIds.length !== NEED[mode()]) calIds = defaultCalIds(); return calIds; }
/* 校正片的名目色（排 S 清單方向、產校正片、帶給校正頁）：庫裡同名料上次量到的色 → 機上那支線材的顏色 → 料槽色 → 灰。
   🔴 只當內部排序用：畫面上的色塊只放量到的色（原型細節 8「不拿擠出機設定色充數」）；量完照片實測值會蓋過它。 */
function calNominal(i){
  const x = ensureCal()[i] || {};
  const k = knownMat(lib(), x.type, x.label);
  if (k && k.hex) return k.hex;
  const f = (page && page.filaments ? page.filaments() : [])[i], cols = page && page.slotColors ? page.slotColors() : [];
  return String((f && f.color) || cols[i] || '#808080').toUpperCase();
}
function calColors(){ return ensureCal().map((_, i) => calNominal(i)); }
/* 第 2、3 步的說明寫料名（顏色名還沒填＝寫「擠出機 N」）。 */
function calNames(){ return ensureCal().map((x, i) => String(x.label || '').trim() || '擠出機 ' + (i + 1)); }
function calMaterials(){ return ensureCal().map(x => ({ type: x.type, label: String(x.label || '').trim() })); }
/* 第 2、3 步說明用的料名（已跳脫——名字是人打的字，說明是 innerHTML）：不給 i＝整組「白 × 深灰」；給 i＝那一支「「白」」（沒填＝空字串）。 */
function calLabelHtml(i){
  if (i == null) return esc(calNames().join(' × '));
  const x = ensureCal()[i], nm = x ? String(x.label || '').trim() : '';
  return nm ? '「' + esc(nm) + '」' : '';
}
function goCal(n){ calStep = Math.max(1, Math.min(5, n)); renderCal(); }
/* 以前量過的那幾對（這次量完會取代它；舊的那一份留作上一版，matlib.upsertPair）。 */
function calSetHint(){
  const xs = calMaterials();
  if (xs.some(x => !x.label) || dupIn(xs)) return '';
  const lb = lib(), old = [];
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++){
    const p = M().findPair(lb, M().makeMaterial(xs[i]), M().makeMaterial(xs[j]));
    if (p) old.push('「' + xs[i].label + ' × ' + xs[j].label + '」' + (mdate(p.measuredAt) ? '（' + mdate(p.measuredAt) + '）' : ''));
  }
  return old.length ? '<div class="calNote">' + esc(old.join('、')) + '以前量過——這次量完會取代它，產圖改用新的；舊的那一份會留著。</div>' : '';
}

/* MIX-01：料位照「人站在機器前」排——雙料 E1 左、E2 右；四料 E1 下左、E2 下右、E3 在 E2 上、E4 在 E1 上。 */
const MIX_ORDER = { 2: [0, 1], 4: [3, 2, 0, 1] };
function renderCal(){
  const doc = root.document; if (!doc) return;
  const md = mode(), n = NEED[md];
  ensureCal();
  doc.querySelectorAll('#calFlow .calStep').forEach(el => {
    const s = +el.getAttribute('data-step');
    el.classList.toggle('now', s === calStep); el.classList.toggle('done', s < calStep);
  });
  const hint = $('calMatsHint');
  if (hint) hint.innerHTML = (md === 'dual' ? '要一起校正的那兩支（雙料＝擠出機 1、2）。' : '要一起校正的那四支——四料會一次校六對（任兩支之間都有）。')
    + '<b>料種＋顏色名</b>就是這支料在材料庫裡的名字；顏色不用填，印出來量到的會自動帶進來。';
  const box = $('calMats');
  if (box){
    box.innerHTML = '<div class="calMatsGrid n' + n + '">' + MIX_ORDER[n].map(i => mpHtml({ i, title: '擠出機 ' + (i + 1), hex: null,
      type: calIds[i].type, name: calIds[i].label, miss: calMiss.indexOf(i) >= 0 })).join('') + '</div><div id="calSetHint">' + calSetHint() + '</div>';
    renderNames();
  }
  const err = $('calMatsErr'); if (err) err.textContent = calErr;
  if (page && page.renderCalSteps) page.renderCalSteps();
  renderCalDone();
}
function onCalInput(e){
  const t = e.target, mp = t.closest ? t.closest('#calMats .mp') : null;
  if (!mp || !calIds) return;
  const i = +mp.getAttribute('data-i'), f = t.getAttribute('data-f');
  if (f === 'name') calIds[i].label = t.value;
  else if (f === 'type') calIds[i].type = t.value;
  else return;
  mpRefresh($('calMats'));
  const sh = $('calSetHint'); if (sh) sh.innerHTML = calSetHint();
  if (page && page.renderCalSteps) page.renderCalSteps();
}
/* 第 1 步 → 第 2 步：顏色名都要填、同一組不能撞名（FBK-11：點下去講缺什麼、標出來）。 */
function calNext(){
  calIds.forEach(x => { x.label = String(x.label || '').trim(); });
  calMiss = calIds.map((x, i) => x.label ? -1 : i).filter(i => i >= 0);
  if (calMiss.length){
    calErr = '請先補上：' + calMiss.map(i => '擠出機 ' + (i + 1) + ' 的顏色名').join('、') + '（已標出來）。';
    renderCal();
    const el = root.document.querySelector('#calMats .mp.miss [data-f=name]'); if (el) el.focus();
    return;
  }
  const dup = dupIn(calIds);
  if (dup){
    calMiss = [dup[1]];
    calErr = '擠出機 ' + (dup[0] + 1) + ' 和擠出機 ' + (dup[1] + 1) + ' 都叫「' + calIds[dup[0]].label + '」，系統會當成同一支料——請改成認得出來的名字（例：白、深灰）。';
    renderCal(); return;
  }
  calErr = ''; calMiss = [];
  goCal(2);
}
/* 校正表收下之後（calibAcceptRaw 成功）。新量的那組直接成為產圖流程的選擇（四料的表在雙料時收下＝進庫、切到四料時選得到）。
   從右欄料單匯入的留在產圖流程講結果；校正流程裡的進第 5 步。 */
function onCalibrated(md, mats){
  const keys = mats.map(m => M().matKey(M().makeMaterial(m)));
  const ok = useKeys(md, keys);
  const names = mats.map(m => m.label).join(' × ');
  if (genAccepting){
    open = false; draft = null;
    flash = ok && md === mode() ? { kind: 'ok', text: '已放進材料庫，產圖改用這組（' + names + '）。' }
      : { kind: ok ? 'ok' : 'warn', text: '已放進材料庫（' + names + '）' + (md !== mode() ? '——這是' + (md === 'quad' ? '四料' : '雙料') + '的一組，切到' + (md === 'quad' ? '四料' : '雙料') + '時選得到。'
          : '，但這組有一對不能用，產圖維持原本那組。') };
    renderPanel(); notify(); return;
  }
  const p = md === 'dual' && mats.length === 2 ? M().findPair(lib(), M().makeMaterial(mats[0]), M().makeMaterial(mats[1])) : null;
  calDoneInfo = { mode: md, mats, used: ok, replaced: p && p.prev ? (p.prev.measuredAt || '') : null,
                  why: ok ? '' : '這組量到的資料有一對不能用（看上面第 4 步的訊息），產圖流程維持原本那組。' };
  goCal(5);
  renderPanel();
  notify();
}
function renderCalDone(){
  const box = $('calDone'); if (!box) return;
  if (calStep < 5 || !calDoneInfo){ box.innerHTML = ''; return; }
  const note = page && page.note ? page.note() : '', R = calDoneInfo;
  box.innerHTML = '<div class="d">這組顏色已經存進材料庫' + (note ? '（⚠ ' + esc(note) + '）' : '') + '。</div>'
    + '<div class="mfTags">' + R.mats.map(m => '<span class="mfTag"><span class="mfSw" style="background:' + esc(m.hex) + '"></span>'
      + esc(m.type ? m.type + ' ' + m.label : m.label) + ' 已校正</span>').join('') + '</div>'
    + (R.replaced !== null ? '<div class="calNote">這組以前量過' + (mdate(R.replaced) ? '（' + mdate(R.replaced) + '）' : '') + '，產圖改用今天這份。</div>' : '')
    + '<div class="sub">' + (R.used ? '產圖流程已改用這組；之後在「選顏色」清單裡也選得到它們。' : esc(R.why)) + '</div>'
    + '<div class="calActs"><button type="button" class="btn primary" data-flow-go="gen">去產圖</button>'
    + '<button type="button" class="btn ghost" data-cal-go="1">再校正另一組</button></div>';
}
function onCalClick(e){
  const u = e.target.closest ? e.target.closest('[data-use]') : null;
  if (u){ useName(u); return; }
  const t = e.target.closest ? e.target.closest('[data-cal-go],[data-flow-go],[data-cal-next]') : null;
  if (!t) return;
  if (t.hasAttribute('data-cal-next')){ calNext(); return; }
  if (t.hasAttribute('data-flow-go')){ setFlow(t.getAttribute('data-flow-go')); return; }
  const n = +t.getAttribute('data-cal-go');
  if (n === 1){ calDoneInfo = null; calIds = defaultCalIds(); calErr = ''; calMiss = []; }
  goCal(n);
}

/* index.html 交進來的轉接物件：
   { lib(), note(), save(), mode(), params(), filaments(), slotColors(), materialTypes(), typesReady(), loading(),
     statusLine(), applied(info), renderCalSteps(), acceptTable(raw, mats, measuredAt) } */
function mount(p){
  page = p;
  remembered = loadRemembered();
  const doc = root.document;
  const panel = $('matPanel'); if (panel) panel.addEventListener('click', onPanelClick);
  const cal = $('calFlow');
  if (cal){ cal.addEventListener('click', onCalClick); cal.addEventListener('input', onCalInput); cal.addEventListener('change', onCalInput); }
  const seg = $('flowSeg');
  if (seg) seg.addEventListener('click', e => { const f = e.target.getAttribute && e.target.getAttribute('data-flow'); if (f) setFlow(f); });
  open = false;
  renderPanel();
  notify(true);
  if (doc) doc.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !dlg) return;
    if (!dlg.back.isConnected){ dlg = null; return; }
    if (dlg.o.esc && dlg.o.on(dlg.o.esc, dlg.back) !== false) closeDlg();
  });
}
/* 庫讀回來／存完／料數變了／料種清單到了 ⇒ 重畫（頁面在這些時間點呼叫）。 */
function refresh(){
  if (!page) return;
  renderPanel();
  if (flow === 'cal') renderCal();
  notify();
  maybeAskLegacy();     // 舊資料那一問：庫與料種清單都到了才問（App 那一份是非同步讀回來的）
}

return {
  NEED, LEVELS_MAX, SEL_KEY, TYPES_FALLBACK,
  pairVerdict, usable, choices, toggle, assignSlots, setInfo, setCheck, validSets, defaultKeys, calibRequestFor, aiPaletteLine,
  typeList, namesOf, nameHint, dupIn, knownMat, mdate, dateFromName, today,
  mount, refresh, ready, info, openPicker, calibRequest, setFlow, calColors, calNames, calLabelHtml, calMaterials, onCalibrated, goCal, importTable,
  flow: () => flow, calStep: () => calStep,
};
});
