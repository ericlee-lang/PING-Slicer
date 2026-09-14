/* =====================================================================
   照片磚色彩校正單元測（0914 Q3 甲，牌 c-0914-PTI-04）
   跑法：node tools/ping/phototile_calib_test.js
   受測＝resources/web/phototile/engine.js 的 calib*／dualLadderCalibrated／quantizeDual／buildCalibStrip。

   紀律：①「calib 缺席 ⇒ 與 dualLadder 逐值相同、quantizeDual 標籤逐位元相同」是保命索，
         沒有這條，改引擎就等於動了所有既有磚的輸出。
         ②正向 oracle 用 0822 那張真表（白×藍，已修正料色）：核心規格 R8-5 記錄的結果
           100/84/69/55/40/26/13/0 → 100/75/61/43/37/31/16/0，這裡逐格斷言。
         ③反向：白×黃（span 4.6）必須被護欄擋下；料色不符必須不套用；apply:false 只做 ④-1。
   ===================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const E = require(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'engine.js'));

/* 0822 兩張真表（Eric 實印＋回讀頁量測，料色已修正＝S=0 那格量到色）。內嵌＝測試自足（原檔在根 repo
   照片磚_色彩校正/measured/，不在本 repo；PING-Slicer 是 PUBLIC repo，這裡只放 8 個量測點、不放整份原檔）。 */
function mkTable(hexA, hexB, pts){
  return { '料數': 2, '校正塊種類': '雙料 8 格（1 對 × 8 階）',
           '料': [{ 槽:'A', 色:hexA, 名:'A' }, { 槽:'B', 色:hexB, 名:'B' }],
           '量測': pts.map(([S, hex], i) => ({ 格:'C'+(i+1), 配方:{ S }, 量到色:hex })) };
}
const TABLE_BLUE = mkTable('#F2F0EB', '#93D9FA', [[1,'#F2F0EB'],[0.86,'#EDF0EF'],[0.71,'#DCEDF3'],[0.57,'#CEEAF6'],[0.43,'#BEE9F9'],[0.29,'#A4E0F8'],[0.14,'#9CDDF9'],[0,'#93D9FA']]);
const TABLE_YELLOW = mkTable('#F2F0EB', '#FBE534', [[1,'#F2F0EB'],[0.86,'#F4F0DE'],[0.71,'#F7F1CC'],[0.57,'#FBF0A1'],[0.43,'#FDEB5B'],[0.29,'#FEE943'],[0.14,'#FDE841'],[0,'#FBE534']]);
const MEAS = path.join(__dirname, '..', '..', '..', '照片磚_色彩校正', 'measured');
function loadTable(name){
  const p = path.join(MEAS, name);                       // 若剛好跑在根 repo 樹下就用原檔，否則用內嵌副本
  if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
  return /藍/.test(name) ? TABLE_BLUE : /黃/.test(name) ? TABLE_YELLOW : null;
}
let pass = 0, fail = 0;
function check(name, fn){
  try { fn(); console.log(`  ✅ ${name}`); pass++; }
  catch (e) { console.log(`  ❌ ${name}\n     ${e && e.stack ? e.stack.split('\n').slice(0,2).join(' | ') : e}`); fail++; }
}
const S = t => Math.round((1 - t) * 100) / 100;
const pct = t => Math.round((1 - t) * 100);

/* 合成一張 4×4 格點影像（只需 w/h/lab；quantizeDual 只讀 lab[p*3]） */
function fakeImg(){
  const w = 4, h = 4, n = w * h;
  const lab = new Float32Array(n * 3);
  for (let p = 0; p < n; p++) { lab[p*3] = 10 + p * (85 / (n - 1)); lab[p*3+1] = 0; lab[p*3+2] = 0; }
  return { w, h, lab, lum: new Float32Array(n), data: new Uint8ClampedArray(n * 4) };
}

(async () => {
  console.log('exports 有校正函式');
  check('calibParseTable／calibGenLadder／dualLadderCalibrated／buildCalibStrip 皆匯出', () => {
    for (const k of ['calibParseTable','calibLookupLin','calibMatches','calibGenLadder','dualLadderCalibrated','buildCalibStrip','buildCalibStripParts','calibStripDefaultS','calibStripGeo'])
      assert(typeof E[k] === 'function', k + ' 缺');
  });

  console.log('\n保命索：calib 缺席 ⇒ 與舊路徑逐值相同');
  const slotsWG = [{ color: '#F2F0EB' }, { color: '#5D6268' }];
  check('dualLadderCalibrated(null) 的 t／LA／LB 與 dualLadder 逐值相同', () => {
    const a = E.dualLadder(slotsWG[0].color, slotsWG[1].color, 8);
    const b = E.dualLadderCalibrated(slotsWG, 8, null);
    assert.deepStrictEqual(b.t, a.t); assert.strictEqual(b.LA, a.LA); assert.strictEqual(b.LB, a.LB);
    assert.strictEqual(b.calib.present, false); assert.strictEqual(b.lookupLin, undefined);
  });
  check('quantizeDual：slots 不帶 calib ⇒ 回傳無 calib 鍵、標籤與 palette 與理論梯相同', async () => {
    const img = fakeImg();
    const P = { klevels: 8 };
    const q = await E._internals.quantizeDual(img, P, slotsWG.map(s => ({ ...s })), null);
    assert(!('calib' in q), '不該有 calib 鍵');
    const lad = E.dualLadder(slotsWG[0].color, slotsWG[1].color, 8);
    assert.deepStrictEqual(q.palette.map(p => p.t), lad.t);
    q.palette.forEach((p, i) => { const t = lad.t[i]; const lin = [0,1,2].map(c => lad.A[c]*(1-t)+lad.B[c]*t); assert.deepStrictEqual(p.lin, lin); });
  });

  console.log('\n正向 oracle：0822 白×藍（已修正料色）＝核心規格 R8-5 記錄的階梯');
  const blue = loadTable('20260822_雙料_白x藍_已修正料色.json');
  const yellow = loadTable('20260822_雙料_白x黃_已修正料色.json');
  if (!blue || !yellow) { console.log('  ⚠ 找不到 measured/ 兩張真表（在根 repo 照片磚_色彩校正/measured/），跳過 oracle'); }
  else {
    const slotsBlue = [{ color: '#F2F0EB' }, { color: '#93D9FA' }];
    check('白×藍 8 階：100/84/69/55/40/26/13/0 → 100/75/61/43/37/31/16/0（R8-5 原紀錄）', () => {
      const theory = E.dualLadder('#F2F0EB', '#93D9FA', 8).t.map(pct);
      assert.deepStrictEqual(theory, [100,84,69,55,40,26,13,0], '理論階梯要先對得上 R8-5 的紀錄');
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: blue, apply: true });
      assert.strictEqual(lad.calib.applied, true, lad.calib.why);
      assert.deepStrictEqual(lad.t.map(pct), [100,75,61,43,37,31,16,0]);
      assert(Math.abs(lad.calib.span - 11.3) < 0.3, 'span≈11.3 L*，得 ' + lad.calib.span);
    });
    check('quantizeDual 帶 calib ⇒ palette 的 t＝校正梯、lin＝實測色（④-1）、回傳 calib 狀態', async () => {
      const img = fakeImg();
      const slots = slotsBlue.map(s => ({ ...s })); slots[0].calib = { table: blue, apply: true };
      const q = await E._internals.quantizeDual(img, { klevels: 8 }, slots, null);
      assert.strictEqual(q.calib.applied, true);
      assert.deepStrictEqual(q.palette.map(p => pct(p.t)), [100,75,61,43,37,31,16,0]);
      const p0 = q.palette[0], p7 = q.palette[7];
      assert.deepStrictEqual(p0.lin, E.calibLookupLin(E.calibParseTable(blue), 1));
      assert.deepStrictEqual(p7.lin, E.calibLookupLin(E.calibParseTable(blue), 0));
    });
    check('apply:false ⇒ 不動 t（理論梯），但 lookupLin 存在（只做 ④-1 顯示）', () => {
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: blue, apply: false });
      assert.strictEqual(lad.calib.applied, false); assert.strictEqual(lad.calib.matches, true);
      assert.deepStrictEqual(lad.t.map(pct), [100,84,69,55,40,26,13,0]);
      assert(typeof lad.lookupLin === 'function');
    });
    check('料色不符 ⇒ 不套用、無 lookupLin、why 講清楚', () => {
      const lad = E.dualLadderCalibrated(slotsWG, 8, { table: blue, apply: true });
      assert.strictEqual(lad.calib.present, true); assert.strictEqual(lad.calib.matches, false);
      assert.strictEqual(lad.calib.applied, false); assert(lad.calib.why.includes('不符'));
      assert.strictEqual(lad.lookupLin, undefined);
      assert.deepStrictEqual(lad.t, E.dualLadder(slotsWG[0].color, slotsWG[1].color, 8).t);
    });
    check('白×黃（L* 跨幅 4.6 < 8）⇒ 護欄③擋下：applied=false、t＝理論梯、why 含「跨幅」', () => {
      const slotsY = [{ color: '#F2F0EB' }, { color: '#FBE534' }];
      const lad = E.dualLadderCalibrated(slotsY, 8, { table: yellow, apply: true });
      assert.strictEqual(lad.calib.matches, true);
      assert.strictEqual(lad.calib.applied, false);
      assert(lad.calib.why.includes('跨幅'), lad.calib.why);
      assert.deepStrictEqual(lad.t, E.dualLadder(slotsY[0].color, slotsY[1].color, 8).t);
    });
    check('壞表 ⇒ present 但 why 說讀不到、不丟例外', () => {
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: { 料數: 4 }, apply: true });
      assert.strictEqual(lad.calib.present, true); assert.strictEqual(lad.calib.applied, false);
      assert(lad.calib.why.includes('讀不到'));
    });
    check('非單調表 ⇒ 護欄④擋下', () => {
      const bad = JSON.parse(JSON.stringify(blue));
      bad['量測'][3]['量到色'] = '#F2F0EB';   // 中段突然回到純白＝非單調
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: bad, apply: true });
      assert.strictEqual(lad.calib.applied, false); assert(lad.calib.why.includes('單調'));
    });
  }

  console.log('\n校正片（直立條）產生器');
  check('calibStripDefaultS：料A 較亮 ⇒ 白端加密；料A 較暗 ⇒ 鏡射到 S≈0 端', () => {
    assert.deepStrictEqual(E.calibStripDefaultS('#F2F0EB', '#5D6268'), [1,0.94,0.87,0.78,0.67,0.53,0.35,0]);
    assert.deepStrictEqual(E.calibStripDefaultS('#5D6268', '#F2F0EB'), [1,0.65,0.47,0.33,0.22,0.13,0.06,0]);
  });
  check('buildCalibStripParts 預設＝v2c 洗料柱版幾何（40×6×16、每階 2 mm、柱 12／gap 8＝0914 實印 12m03s 那條）', () => {
    /* v1（80×8×48、每階 6 mm、無柱、實印 32m45s）已作廢：Eric 0914 裁「建議還是使用洗料塔」＋「不要印那麼久」。
       幾何的唯一來源＝engine.js 的 CALIB_STRIP_GEO；頁面不得再自己寫一份（v1／v2c 分叉就是那樣來的）。 */
    assert.deepStrictEqual(E.calibStripGeo(), { widthMm: 40, thickMm: 6, bandMm: 2, purgeMm: 12, purgeGapMm: 8, purgeWalls: 2 });
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰' });
    assert.strictEqual(c.width, 40); assert.strictEqual(c.thick, 6);
    assert.strictEqual(c.band, 2);   assert.strictEqual(c.height, 16);      // 8 階 × 2 mm
    assert.strictEqual(c.purge, 12); assert.strictEqual(c.purgeGap, 8); assert.strictEqual(c.purgeWalls, 2);
  });
  check('buildCalibStripParts：8 片＋8 柱、片名 S1／…／S0、柱名「洗料柱NN … S…」、只有片的正／背面禁縫', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰' });
    const names = [...c.cfg.matchAll(/key="name" value="([^"]+)"/g)].map(m => m[1]);
    assert.strictEqual(names.length, 18);   // 柱物件名＋8 柱零件＋片物件名＋8 片零件
    const ladder = ['S1', 'S0.94', 'S0.87', 'S0.78', 'S0.67', 'S0.53', 'S0.35', 'S0'];
    assert.deepStrictEqual(names.slice(1, 9).map(n => n.split(' ').pop()), ladder);    // 柱段
    assert.deepStrictEqual(names.slice(10).map(n => n.split(' ').pop()), ladder);      // 片段
    assert(names.slice(1, 9).every(n => /^洗料柱\d\d /.test(n)), '柱零件名認不出來：' + names.slice(1, 9).join('｜'));
    assert(names.slice(10).every(n => /^校正\d\d /.test(n)), '片零件名認不出來：' + names.slice(10).join('｜'));
    assert.strictEqual((c.model.match(/paint_seam="8"/g) || []).length, 8 * 4);        // 每階正／背面各 2 三角形；柱不標
    assert(!/paint_seam="4"/.test(c.model), '直立條不標接著面');
    assert(c.model.includes('PING-PhotoTile-ColorCalib'));
    /* 柱要是空心方管：0% 填充、2 圈牆、無上下殼——實心柱＝白燒料與時間 */
    assert.strictEqual((c.cfg.match(/key="sparse_infill_density" value="0%"/g) || []).length, 8);
    assert.strictEqual((c.cfg.match(/key="wall_loops" value="2"/g) || []).length, 8);
    assert.strictEqual((c.cfg.match(/key="top_shell_layers" value="0"/g) || []).length, 8);
  });
  check('🔴 柱段與片段的 extruder 逐階相同（同一個 M6051 配方，柱才洗得到那一階的殘料）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268' });
    const objs = [...c.cfg.matchAll(/<object id="(\d+)">([\s\S]*?)<\/object>/g)]
      .map(m => ({ id: m[1], ex: [...m[2].matchAll(/key="extruder" value="(\d+)"/g)].map(x => Number(x[1])) }));
    const tower = objs.find(o => o.id === '2000'), strip = objs.find(o => o.id === '1000');
    assert(tower && strip, 'cfg 要有 2000（柱）與 1000（片）兩顆物件，實得 ' + objs.map(o => o.id).join(','));
    assert.deepStrictEqual(strip.ex, [1, 2, 3, 4, 5, 6, 7, 8]);
    assert.deepStrictEqual(tower.ex, strip.ex);   // 不同＝柱洗的是別階的料，整條校正片作廢
  });
  check('柱的 build item 排在片之前（切片器逐層先印柱）＋「片＋柱」整組置中（3MF 座標＝G-code 座標）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268' });
    const items = [...c.model.matchAll(/<item objectid="(\d+)" transform="1 0 0 0 1 0 0 0 1 (\S+) (\S+) 0"/g)]
      .map(m => ({ id: m[1], x: Number(m[2]), y: Number(m[3]) }));
    assert.deepStrictEqual(items.map(i => i.id), ['2000', '1000']);   // 柱在前＝每層先印它
    /* 0914 v2 實切踩過：沒置中時 3MF 寫柱在 X 40~55，切片器整組置中後 G-code 落在 28~42
       ⇒ 產生器要先把聯集包圍盒置中，txt 報的 --purge-box 才對得上真實 G-code。 */
    const st = items[1], tw = items[0];
    assert.strictEqual((Math.min(st.x, tw.x) + Math.max(st.x + c.width, tw.x + c.purge)) / 2, 0, 'X 未置中');
    assert.strictEqual((Math.min(st.y, tw.y) + Math.max(st.y + c.thick, tw.y + c.purge)) / 2, 0, 'Y 未置中');
    assert.deepStrictEqual(c.purgeBox, { x0: 18, y0: -6, x1: 30, y1: 6 });
    assert(c.txt.includes('--purge-box 18,-6,30,6'), 'ping_calib.txt 要直接報 verify 參數，省得下一棒自己算');
  });
  check('與 python 參考正本 make_calib_3mf.py v2c 產物逐位元組相同（3dmodel.model 的 sha256）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268' });
    const got = require('crypto').createHash('sha256').update(c.model, 'utf8').digest('hex');
    /* 這顆值的來源＝0914 **實印驗證過**的那一條：根 repo
         照片磚_色彩校正/色彩校正_白深灰_8階_v2c洗料柱_FD300_0.4.3mf 裡的 3D/3dmodel.model
       （產生指令 make_calib_3mf.py --pair white-gray --width 40 --thick 6 --band 2 --purge 12 --purge-gap 8；
         r1 切片 80 層／2.76 g／估 13m26s，.186 實印 12m03s，Eric 拍照後建表成功）。
       3dmodel.model 不含 title ⇒ 這顆 hash 只釘幾何與命名結構，不受 --title 影響。
       🔴 要改這顆值之前先回答一句：新幾何實印驗證過了嗎？沒有就不要改它，改的是程式。 */
    assert.strictEqual(got, '43062b6ce39a96aeb4c18561a92d04e59a86fff33edda73dcaa72982ca191717');
  });
  check('purgeMm:0 ⇒ 退回無柱幾何（只給離線對照用；build item 剩一個、仍置中）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', purgeMm: 0, widthMm: 80, thickMm: 8, bandMm: 6 });
    assert.strictEqual(c.height, 48);
    assert.strictEqual(c.purgeBox, null);
    assert.strictEqual((c.model.match(/<item /g) || []).length, 1);
    assert(!/洗料柱/.test(c.cfg));
  });
  check('buildCalibStrip：makeZip 出 Blob，5 個 entry，體積 >2 KB', async () => {
    const r = await E.buildCalibStrip({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰' });
    assert(r.blob && r.blob.size > 2000, 'blob 太小 ' + (r.blob && r.blob.size));
    const bytes = new Uint8Array(await r.blob.arrayBuffer());
    let cnt = 0; for (let i = 0; i + 4 <= bytes.length; i++) if (bytes[i]===0x50&&bytes[i+1]===0x4b&&bytes[i+2]===0x03&&bytes[i+3]===0x04) cnt++;
    assert.strictEqual(cnt, 5);
  });
  check('端點不是純色 ⇒ 拒產', () => {
    assert.throws(() => E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', s: [0.9, 0.5, 0] }), /純色錨點/);
  });

  console.log('\n乙案色調映射（toneStretch；0914 三色巴哥中間階空掉的實錄）');
  /* 三色圖：L* 5／45／95 各三分之一（AI 壓平巴哥的直方圖形狀）；料＝白 95 × 深灰 48 */
  function triImg(){
    const w = 30, h = 30, n = w * h; const lab = new Float32Array(n * 3);
    for (let p = 0; p < n; p++) lab[p*3] = p % 3 === 0 ? 5 : p % 3 === 1 ? 45 : 95;
    return { w, h, lab, lum: new Float32Array(n), data: new Uint8ClampedArray(n * 4) };
  }
  const tableGray = mkTable('#F2F0EB', '#707279', [[1,'#F2F0EB'],[0.94,'#DFDDD9'],[0.87,'#C1C0C0'],[0.78,'#B7B6B8'],[0.67,'#9B9BA0'],[0.53,'#94979E'],[0.35,'#777A81'],[0,'#707279']]);
  const slotsGray = [{ color: '#F2F0EB' }, { color: '#707279' }];
  const hist = q => { const c = {}; for (const v of q.rawLabels) c[v] = (c[v] || 0) + 1; return c; };
  check('套表、不開 toneMap ⇒ 圖裡 L*45 的灰與 L*5 的黑都夾成最深階（中間階空）', async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: true };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    const h = hist(q); assert.strictEqual(h[1] || 0, 0, '中間階應為空'); assert(h[0] > 0 && h[2] > 0);
    assert.strictEqual(q.calib.toneMap, undefined);
  });
  check("套表＋toneMap:'stretch' ⇒ 三階都有像素（各三分之一），calib.toneMap 記錄映射範圍", async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: true, toneMap: 'stretch' };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    const h = hist(q); assert(h[0] > 0 && h[1] > 0 && h[2] > 0, JSON.stringify(h));
    assert.strictEqual(h[0], h[1]); assert.strictEqual(h[1], h[2]);
    assert.strictEqual(q.calib.toneMap.mode, 'stretch'); assert(q.calib.toneMap.Lmin <= 5.5 && q.calib.toneMap.Lmax >= 94.5);
  });
  check("apply:false＋toneMap:'stretch' ⇒ 不映射（映射只跟著 ④-2 走）", async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: false, toneMap: 'stretch' };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    assert.strictEqual(q.calib.toneMap, undefined);
  });
  check('toneStretch 本身：百分位夾住、映射到 [dark, light] 兩端', () => {
    const im = triImg(); const ts = E.toneStretch(im.lab, im.w * im.h, 95, 48.3, {});
    assert(Math.abs(ts.mapL(5) - 48.3) < 1e-6 && Math.abs(ts.mapL(95) - 95) < 1e-6);
    assert(ts.mapL(45) > 60 && ts.mapL(45) < 80, 'L*45 應落在中段（得 ' + ts.mapL(45) + '）');
  });

  console.log(`\n${pass} 通過、${fail} 失敗`);
  process.exit(fail ? 1 : 0);
})();
