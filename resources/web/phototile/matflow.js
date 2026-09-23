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

/* 一組已選齊的料 → 槽位、料色、色階上限、要不要認領。回 null＝這組不成立（例如選好之後庫被改過）。 */
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
  const claim = [];
  pairs.forEach(v => { if (M().needsClaim(v.pair) && !v.pair.claimSkippedAt) claim.push(v.pair); });
  return { info: { mode, keys: mats.map(m => m.key), mats, colors, pairs, span, cap, warn: warn.join('；'), claim }, why: '' };
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

/* ================= 畫面（只在瀏覽器） ================= */

let page = null;              // index.html 交進來的轉接物件（見 mount）
let flow = 'gen';             // gen＝產圖流程｜cal＝校正流程
let open = false;             // 使用者自己打開第 1 步（按「換一組…」）。還沒有可用的那組時，不論這個旗標都是展開的——
                              // 🔴 兩件事不能混成一個旗標：App 的庫是非同步讀回來的，讀回來自動選好一組之後要自己收起（段 F 截圖抓到）
let draft = null;             // 展開時正在點的那組（選齊才生效；沒選齊就收起＝維持原本那組）
let flash = '';               // 點到選不到的列時的說明
const applied = { dual: null, quad: null };   // 生效中的那組（setInfo 的結果）
let remembered = { dual: [], quad: [] };
let calStep = 1, calIds = null, calDoneInfo = null;

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

/* 目前這個料數（或指定料數）生效中的那組；庫變了（認領、重量測）就重算，不成立就退回預設。 */
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
function openPicker(){ if (flow !== 'gen') setFlow('gen'); open = true; draft = null; flash = ''; renderPanel(); scrollPanel(); }
function calibRequest(){ return calibRequestFor(lib(), current(), page && page.params()); }

function useKeys(md, keys){
  const inf = setInfo(lib(), md, keys);
  if (!inf) return false;
  applied[md] = inf; remembered[md] = inf.keys.slice(); saveRemembered();
  return true;
}

/* ---- 擠出機小色塊（列印模擬標題列；Eric 0919：「這樣我也知道擠出機 1 跟擠出機 2 我要放什麼料」）---- */
function chipsHtml(n){
  const inf = current();
  let h = '<span class="extPre">擠出機</span>';
  for (let i = 0; i < n; i++){
    const m = inf && inf.mats[i], c = inf && inf.colors[i];
    h += '<button type="button" class="ext" data-mf="open" title="' + esc('擠出機 ' + (i + 1) + '：' + (m ? m.label + '（' + c + '）' : '還沒選') + '\n點一下換一組顏色') + '">'
       + '<span class="mfSw' + (m ? '' : ' none') + '"' + (m ? ' style="background:' + esc(c) + '"' : '') + '></span>'
       + '<span class="extW">擠出機 </span>' + (i + 1) + '</button>';
  }
  return h;
}

/* ---- 產圖流程第 1 步 ---- */
function renderPanel(){
  const box = $('matPanel'); if (!box) return;
  const md = mode(), need = NEED[md], lb = lib(), inf = current();
  const mats = M().listMaterials(lb);
  const note = page && page.note ? page.note() : '';
  const noteHtml = note ? '<div class="sub warn">⚠ ' + esc(note) + '</div>' : '';
  if (!mats.length && page && page.loading && page.loading()){
    /* App 那一份是非同步讀回來的：讀回來之前庫是空的，但那不是「你沒有校正過」——講實話，不先嚇人。 */
    box.innerHTML = '<h2><span class="mfNo">1</span>選顏色</h2><div class="pad"><div class="sub">正在讀取材料庫…</div></div>';
    return;
  }
  if (!mats.length){
    box.innerHTML = '<h2><span class="mfNo">1</span>選顏色</h2><div class="pad"><div class="mfEmpty">'
      + '<b>還沒有校正過的顏色。</b><br>沒量過的料，系統不知道它印出來是什麼顏色，所以這裡選不到。'
      + '先校正一組料（印一片校正片、拍一張照），它就會出現在這裡。'
      + '<div class="mfActs"><button type="button" class="btn primary" data-mf="tocal">去校正一組料</button>'
      + '<button type="button" class="btn ghost" data-mf="import">匯入校正表…</button></div></div>' + noteHtml + '</div>';
    return;
  }
  if (!open && inf){
    /* 收起時只有一行（左欄多一塊就把款式卡往摺線下推：1920 寬實量第 1 步佔 81 px）。
       說明那一行「平時安靜、異常才出聲」（七律#2 增補實例）：上限被壓低、資料有疑慮、校正值沒套用、存不進去，才展開講。
       ⛔ 列印內容用的不是實測值時一定要看得到（R8-5「摘要行不准只講好消息」）——狀態文字由頁面依這次模擬的結果寫。 */
    const st = page && page.statusLine ? page.statusLine() : '';
    box.innerHTML = '<h2><span class="mfNo">1</span>顏色<span class="mfSum">'
      + inf.mats.map((m, i) => '<span class="mfSw" style="background:' + esc(inf.colors[i]) + '"></span>' + esc(m.label)).join('<span class="mfX">×</span>')
      + '</span><span class="hint">最多 ' + inf.cap + ' 階</span><button type="button" class="btn ghost" data-mf="open">換一組…</button></h2>'
      + ((inf.cap < LEVELS_MAX || st || inf.warn || noteHtml)
        ? '<div class="pad mfMeta">' + (inf.cap < LEVELS_MAX ? capLine(inf) : '')
          + '<div class="sub warn" id="mfStatus">' + esc(st) + '</div>'
          + (inf.warn ? '<div class="sub warn">⚠ 資料有疑慮但不擋：' + esc(inf.warn) + '</div>' : '') + noteHtml + '</div>'
        : '');
    return;
  }
  const d = draft && draft.mode === md ? draft.picked : (inf ? inf.keys.slice() : []);
  const ch = choices(lb, md, d);
  let h = '<h2><span class="mfNo">1</span>選顏色<span class="hint">' + (md === 'dual' ? '雙料，挑 2 支' : '四料，挑 4 支') + '</span>'
        + (inf ? '<button type="button" class="btn ghost" data-mf="close">收起</button>' : '') + '</h2><div class="pad">'
        + '<div class="sub">清單只有校正過的料——沒量過的料，系統不知道它印出來是什麼顏色，所以選不到。</div>'
        + '<table class="mfTable"><thead><tr><th>選</th><th>材料</th><th>料色</th></tr></thead><tbody>';
  ch.rows.forEach(r => {
    const m = r.mat;
    h += '<tr class="mfRow ' + r.state + '" data-key="' + esc(m.key) + '">'
       + '<td><span class="mfPick' + (r.state === 'picked' ? ' on' : '') + '">' + (r.state === 'picked' ? (r.order + 1) : (r.state === 'no' ? '🔒' : '')) + '</span></td>'
       + '<td>' + esc(m.label) + (r.state === 'no' ? '<div class="mfWhy">' + esc(r.why) + '</div>' : '') + '</td>'
       + '<td><span class="mfSw" style="background:' + esc(m.hex) + '"></span> <code>' + esc(m.hex) + '</code></td></tr>';
  });
  h += '</tbody></table>';
  const miss = need - ch.picked.length;
  h += '<div class="sub mfNow">' + (ch.picked.length ? '已點：' + ch.picked.map(k => esc((ch.rows.find(r => r.mat.key === k) || {}).mat.label)).join('、') : '還沒點')
     + (miss > 0 ? '（還缺 ' + miss + ' 支；選齊就生效——最淺的那支自動放擠出機 1，其餘照你點的順序）' : '') + '</div>';
  if (flash) h += '<div class="mfFlash">' + esc(flash) + '（下面的「去校正一組料」）</div>';
  h += '<div class="mfExit">沒有想要的顏色？<button type="button" class="btn ghost" data-mf="tocal">去校正一組料</button>'
     + '<button type="button" class="btn ghost" data-mf="import">匯入校正表…</button><span class="sub">校正完成之後它就會出現在這張清單裡。</span></div>'
     + noteHtml + '</div>';
  box.innerHTML = h;
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
  if (act === 'open'){ open = true; draft = null; flash = ''; renderPanel(); scrollPanel(); return; }
  if (act === 'close'){ open = false; draft = null; flash = ''; renderPanel(); return; }
  if (act === 'tocal'){ setFlow('cal'); return; }
  if (act === 'import'){ setFlow('cal'); goCal(4); const f = $('calibFile'); if (f) f.click(); return; }
  const key = t.getAttribute('data-key');
  if (!key) return;
  const md = mode(), inf = current();
  const base = draft && draft.mode === md ? draft.picked : (inf ? inf.keys.slice() : []);
  const ch = choices(lib(), md, base);
  const row = ch.rows.find(r => r.mat.key === key);
  if (!row) return;
  if (row.state === 'no'){ flash = '「' + row.mat.label + '」選不到：' + row.why + '。要用它，先把這組料一起校正。'; renderPanel(); return; }
  flash = '';
  const next = toggle(ch.picked, key, ch.need);
  draft = { mode: md, picked: next };
  if (next.length === ch.need){
    const chk = setCheck(lib(), md, next);
    if (chk.info && useKeys(md, next)){ open = false; draft = null; changed(); return; }
    flash = '這組選不起來：' + chk.why + '。';
  }
  renderPanel();
}
function scrollPanel(){ const b = $('matPanel'); if (b && b.scrollIntoView) b.scrollIntoView({ block: 'nearest' }); }

/* 選的那組變了 ⇒ 交回頁面（寫料槽、壓色階上限、重算）。只在真的變了才交：頁面收到之後會重畫料槽、
   又呼叫回 refresh()——用簽章擋住，不會繞圈。庫讀回來（App 是非同步）、收下新表、認領，都走這一支。 */
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
  maybeClaim();
}

/* ---- 認領（R6-14 子題 2 附款，Eric 2026-09-22 裁 Q1「要」；一次性、可跳過）----
   舊表遷進來的、匯入的表沒有 filament_id ⇒ 第一次在產圖流程選到時問一次「請指給現在的哪幾支線材」。
   選項＝App 回報的機上線材（段 B 的 filaments）；瀏覽器直開沒有這份清單 ⇒ 不問（問了也沒得選）。 */
let claimOpen = false, claimEsc = null, claimBack = null;
const claimLater = new Set();       // 按 Esc 關掉的＝這次先不問（不記進庫；下次開工作室再問）
function maybeClaim(){
  /* 頁面別的對話框（例如載圖時問題材）會把 .cfmBack 全部拿掉——被拿掉就當成這次沒問，狀態要跟著放開。 */
  if (claimOpen && claimBack && !claimBack.isConnected){ claimOpen = false; claimEsc = null; }
  const inf = current();
  const fil = page && page.filaments ? page.filaments() : [];
  if (claimOpen || flow !== 'gen' || !inf || !fil.length || !root.document) return;
  if (root.document.querySelector('.cfmBack')) return;   // 別的對話框開著：不疊上去，下次 refresh 再問
  if (!inf.claim.some(p => !claimLater.has(p.id))) return;
  const mats = inf.mats.filter(m => !m.fid);
  if (!mats.length) return;
  claimOpen = true;
  const date = inf.claim.map(p => p.measuredAt).filter(Boolean).sort()[0];
  const at = date ? ' ' + date + ' ' : '之前';                // 舊表沒有日期：讀成「這組是之前校正的…」，不要「這組是 之前 校正的」
  const back = root.document.createElement('div'); back.className = 'cfmBack';
  claimBack = back;
  /* 預設指給同一個槽位的那支（inf.mats 已照槽位排＝擠出機順序）；人可以改。 */
  const optsAt = sel => fil.map((f, i) => '<option value="' + i + '"' + (i === sel ? ' selected' : '') + '>'
    + esc('擠出機 ' + (i + 1) + '：' + (f.name || f.id || '') + (f.color ? '　' + String(f.color).toUpperCase() : '')) + '</option>').join('');
  back.innerHTML = '<div class="cfmBox mfClaim" role="dialog" aria-modal="true">'
    + '<div class="cfmTitle">這組是' + esc(at) + '校正的 ' + inf.mats.map(m => esc(m.label)).join('×') + '，請指給現在的哪幾支線材？</div>'
    + '<div class="cfmBody">只問這一次。指定之後，換機器或改料名都認得出它；跳過也可以，那這組只能靠顏色比對。</div>'
    + mats.map(m => '<div class="mfClaimRow" data-key="' + esc(m.key) + '"><span class="mfSw" style="background:' + esc(m.hex) + '"></span>'
        + '<b>' + esc(m.label) + '</b> → <select>' + optsAt(Math.min(fil.length - 1, inf.mats.indexOf(m))) + '</select>'
        + '<input type="text" value="' + esc(m.label) + '" placeholder="標籤（例：白、深灰）"></div>').join('')
    + '<div class="cfmBtns"><button type="button" class="btn primary" data-c="yes">指定</button>'
    + '<button type="button" class="btn" data-c="no">跳過，之後不再問</button></div></div>';
  root.document.body.appendChild(back);
  const close = () => { back.remove(); claimOpen = false; claimEsc = null; };
  claimEsc = () => { inf.claim.forEach(p => claimLater.add(p.id)); close(); };
  back.addEventListener('click', ev => {
    const c = ev.target.getAttribute && ev.target.getAttribute('data-c');
    if (!c) return;
    const lb = lib(), now = new Date().toISOString().slice(0, 10);
    if (c === 'no'){ inf.claim.forEach(p => { const q = M().getPair(lb, p.id); if (q) q.claimSkippedAt = now; }); }
    else {
      const map = new Map();
      back.querySelectorAll('.mfClaimRow').forEach(r => {
        const f = fil[+r.querySelector('select').value] || {}, k = r.getAttribute('data-key');
        const label = r.querySelector('input').value.trim() || (inf.mats.find(m => m.key === k) || {}).label || f.name || '料';
        map.set(k, { fid: f.id ? String(f.id) : null, label });
      });
      const keys = claimMaterials(lb, map, now);
      if (keys) useKeys(mode(), inf.keys.map(k => keys.get(k) || k));
    }
    if (page) page.save();
    close(); renderPanel(); notify();
  });
}
/* 材料層級的認領：一支料出現在好幾對裡，每一對都要換成新身分。回傳 舊 key → 新 key。
   🔴 新身分撞到庫裡已經有的一對＝那一對留原樣（不拿舊資料蓋新資料），這一對標「已跳過」。 */
function claimMaterials(lb, map, now){
  const keyOf = m => M().matKey(m), renamed = new Map();
  map.forEach((v, k) => renamed.set(k, M().matKey(M().makeMaterial({ fid: v.fid, label: v.label, hex: '#000000' }))));
  lb.pairs.slice().forEach(p => {
    const ka = keyOf(p.a), kb = keyOf(p.b);
    if (!map.has(ka) && !map.has(kb)) return;
    const na = map.has(ka) ? Object.assign({}, map.get(ka), { hex: p.a.hex }) : p.a;
    const nb = map.has(kb) ? Object.assign({}, map.get(kb), { hex: p.b.hex }) : p.b;
    const nid = M().pairId(M().makeMaterial(na), M().makeMaterial(nb));
    if (nid !== p.id && M().getPair(lb, nid)){ p.claimSkippedAt = now; return; }
    M().claimPair(lb, p.id, na, nb, { claimedAt: now });
  });
  return renamed;
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
  else { open = false; renderPanel(); notify(); }
}

/* ---- 校正流程 ---- */
/* 第 1 步「放一組料」的預設＝機上那幾支（App 回報的 filaments；料 N＝擠出機 N）。
   🔴 身分（filament_id＋標籤）在這一步由人確認，**不從校正片去猜哪一端是哪一支**（段 B 的界線）。
   標籤預設帶「料名・色碼」：同一支 preset 可能裝了兩捲不同顏色（R6-14 子題 1），只帶料名兩端會撞成同一支料。 */
function defaultCalIds(){
  const n = NEED[mode()], fil = page && page.filaments ? page.filaments() : [];
  const cols = page && page.slotColors ? page.slotColors() : [];
  const out = [];
  for (let i = 0; i < n; i++){
    const f = fil[i];
    const hex = String((f && f.color) || cols[i] || '#808080').toUpperCase();
    out.push(f ? { fi: i, fid: f.id ? String(f.id) : null, name: f.name || '', label: autoLabel(f.name, hex), hex }
               : { fi: -1, fid: null, name: '', label: hex, hex });
  }
  return out;
}
function autoLabel(name, hex){ return (name ? name + '・' : '') + hex; }
function calColors(){ return (calIds || defaultCalIds()).map(x => x.hex); }
function calMaterials(){ return (calIds || defaultCalIds()).map(x => ({ fid: x.fid, label: x.label, hex: x.hex })); }
function goCal(n){ calStep = Math.max(1, Math.min(5, n)); renderCal(); }

/* MIX-01：料位照「人站在機器前」排——雙料 E1 左、E2 右；四料 E1 下左、E2 下右、E3 在 E2 上、E4 在 E1 上。 */
const MIX_ORDER = { 2: [0, 1], 4: [3, 2, 0, 1] };
function renderCal(){
  const doc = root.document; if (!doc) return;
  const md = mode(), n = NEED[md];
  if (!calIds || calIds.length !== n) calIds = defaultCalIds();
  const fil = page && page.filaments ? page.filaments() : [];
  doc.querySelectorAll('#calFlow .calStep').forEach(el => {
    const s = +el.getAttribute('data-step');
    el.classList.toggle('now', s === calStep); el.classList.toggle('done', s < calStep);
  });
  const hint = $('calMatsHint');
  if (hint) hint.textContent = md === 'dual' ? '要一起校正的那兩支（雙料＝擠出機 1、2）。'
                                            : '要一起校正的那四支——四料會一次校六對（任兩支之間都有）。';
  const box = $('calMats');
  if (box){
    box.className = 'calMats n' + n;
    box.innerHTML = MIX_ORDER[n].map(i => {
      const x = calIds[i];
      const sel = fil.length ? '<label>線材 <select data-i="' + i + '" data-k="fid">' + fil.map((f, j) =>
        '<option value="' + j + '"' + (j === x.fi ? ' selected' : '') + '>'
        + esc('擠出機 ' + (j + 1) + ' 上的 ' + (f.name || f.id || '')) + '</option>').join('') + '</select></label>' : '';
      return '<div class="calMat"><div class="calMatT">擠出機 ' + (i + 1) + '</div>' + sel
        + '<label>顏色 <input type="color" data-i="' + i + '" data-k="hex" value="' + esc(x.hex.toLowerCase()) + '"></label>'
        + '<label class="lbl">標籤 <input type="text" data-i="' + i + '" data-k="label" value="' + esc(x.label) + '"></label></div>';
    }).join('');
  }
  const err = $('calMatsErr'); if (err) err.textContent = '';
  if (page && page.renderCalSteps) page.renderCalSteps();
  renderCalDone();
}
function onCalInput(e){
  const t = e.target, i = +t.getAttribute('data-i'), k = t.getAttribute('data-k');
  if (!calIds || !calIds[i] || !k) return;
  const x = calIds[i], auto = x.label === autoLabel(x.name, x.hex);   // 標籤還是預設帶的 ⇒ 跟著改；人改過就不動
  if (k === 'fid'){
    if (e.type !== 'change') return;
    const f = page.filaments()[+t.value] || {};
    x.fi = +t.value; x.fid = f.id ? String(f.id) : null; x.name = f.name || '';
    if (f.color) x.hex = String(f.color).toUpperCase();
    if (auto) x.label = autoLabel(x.name, x.hex);
    renderCal(); return;
  }
  if (k === 'hex'){
    x.hex = String(t.value).toUpperCase();
    if (auto) x.label = autoLabel(x.name, x.hex);
    if (e.type === 'change') renderCal();
    return;
  }
  if (k === 'label') x.label = t.value;
}
/* 第 1 步 → 第 2 步：標籤不能空、兩支不能撞成同一支（身分＝filament_id＋標籤）。 */
function calNext(){
  const keys = calIds.map(x => M().matKey({ fid: x.fid, label: String(x.label || '').trim() }));
  const err = $('calMatsErr');
  if (calIds.some(x => !String(x.label || '').trim())){ if (err) err.textContent = '每一支都要有標籤（讓你之後在清單上認得出這捲料）。'; return; }
  if (new Set(keys).size !== keys.length){ if (err) err.textContent = '有兩支的料與標籤完全一樣，系統會當成同一支——請把標籤改成認得出來的名字（例：白、黑）。'; return; }
  calIds.forEach(x => { x.label = String(x.label).trim(); });
  goCal(2);
}
/* 校正表收下之後（calibAcceptRaw 成功）＝第 5 步；新量的那組直接成為產圖流程的選擇。 */
function onCalibrated(md, mats){
  const keys = mats.map(m => M().matKey(M().makeMaterial(m)));
  const ok = useKeys(md, keys);
  calDoneInfo = { mode: md, mats, used: ok, why: ok ? '' : '這組量到的資料有一對不能用（看上面第 4 步的訊息），產圖流程維持原本那組。' };
  goCal(5);
  renderPanel();
  notify();
}
function renderCalDone(){
  const box = $('calDone'); if (!box) return;
  if (calStep < 5 || !calDoneInfo){ box.innerHTML = ''; return; }
  const note = page && page.note ? page.note() : '';
  box.innerHTML = '<div class="d">這組顏色已經存進材料庫' + (note ? '（⚠ ' + esc(note) + '）' : '') + '。</div>'
    + '<div class="mfTags">' + calDoneInfo.mats.map(m => '<span class="mfTag"><span class="mfSw" style="background:' + esc(m.hex) + '"></span>' + esc(m.label) + ' 已校正</span>').join('') + '</div>'
    + '<div class="sub">' + (calDoneInfo.used ? '產圖流程已改用這組；之後在「選顏色」清單裡也選得到它們。' : esc(calDoneInfo.why)) + '</div>'
    + '<div class="calActs"><button type="button" class="btn primary" data-flow-go="gen">去產圖</button>'
    + '<button type="button" class="btn ghost" data-cal-go="1">再校正另一組</button></div>';
}
function onCalClick(e){
  const t = e.target.closest ? e.target.closest('[data-cal-go],[data-flow-go],[data-cal-next]') : null;
  if (!t) return;
  if (t.hasAttribute('data-cal-next')){ calNext(); return; }
  if (t.hasAttribute('data-flow-go')){ setFlow(t.getAttribute('data-flow-go')); return; }
  const n = +t.getAttribute('data-cal-go');
  if (n === 1){ calDoneInfo = null; calIds = defaultCalIds(); }
  goCal(n);
}

/* index.html 交進來的轉接物件：
   { lib(), note(), save(), mode(), params(), filaments(), slotColors(), applied(info), renderCalSteps() } */
function mount(p){
  page = p;
  remembered = loadRemembered();
  const doc = root.document;
  const panel = $('matPanel'); if (panel) panel.addEventListener('click', onPanelClick);
  const cal = $('calFlow');
  if (cal){ cal.addEventListener('click', onCalClick); cal.addEventListener('input', onCalInput); cal.addEventListener('change', onCalInput); }
  const seg = $('flowSeg');
  if (seg) seg.addEventListener('click', e => { const f = e.target.getAttribute && e.target.getAttribute('data-flow'); if (f) setFlow(f); });
  const sl = $('slotList');
  if (sl) sl.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-mf="open"]')) openPicker(); });
  open = false;
  renderPanel();
  notify(true);
  if (doc) doc.addEventListener('keydown', ev => { if (ev.key === 'Escape' && claimEsc) claimEsc(); });
}
/* 庫讀回來／存完／料數變了 ⇒ 重畫（頁面在這些時間點呼叫）。 */
function refresh(){
  if (!page) return;
  renderPanel();
  if (flow === 'cal') renderCal();
  notify();
  maybeClaim();          // 開工作室時自動選到、而那組還沒認領＝也算「第一次在產圖流程選到」；機上線材要等 App 回報才有
}

return {
  NEED, LEVELS_MAX, SEL_KEY,
  pairVerdict, usable, choices, toggle, assignSlots, setInfo, setCheck, validSets, defaultKeys, calibRequestFor, aiPaletteLine, claimMaterials,
  mount, refresh, ready, info, openPicker, calibRequest, chipsHtml, setFlow, calColors, calMaterials, onCalibrated, goCal,
  flow: () => flow, calStep: () => calStep,
};
});
