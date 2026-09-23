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
const M = require(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'matlib.js'));
const ML_SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'matlib.js'), 'utf8');

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
/* 🔴 **check 必須 await fn()**：測試體是 async 時，`fn()` 只跑到第一個 await 就回傳 Promise，
   後面的 assert 變成 unhandled rejection，而這裡已經印了 ✅、最後又 process.exit ⇒ **失敗會被報成通過**。
   0922 實測：一個「await 之後才丟」的測試體，舊版 check 報 OK。修的是源頭（本函式），
   不是逐條測試——另見下面第一組「harness 自我陽性對照」，沒有它，這個坑會再回來一次而且沒人看得見。 */
async function check(name, fn){
  try { await fn(); console.log(`  ✅ ${name}`); pass++; }
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
  /* 🔒 **harness 自我陽性對照**：全綠而沒有陽性對照，等於不知道測試有沒有在測東西。
     這一組不測引擎，測的是 **check 自己抓不抓得到失敗**（同步與非同步各一條）。
     0922 實測：舊版 check 沒 await fn()，「await 之後才丟」的測試體被報成 ✅
     ⇒ 四條 quantizeDual 斷言實際一直是空的，而畫面上看起來 33/0 全過。 */
  {
    const probe = async fn => { try { await fn(); return 'no-throw'; } catch (e) { return 'caught'; } };
    const syncCaught  = await probe(async () => { let p=0,f=0;
      const c = async (n_, fn_) => { try { await fn_(); p++; } catch(e){ f++; } };
      await c('x', () => { throw new Error('boom'); });
      assert.strictEqual(f, 1, '同步失敗沒被算成 fail'); });
    const asyncCaught = await probe(async () => { let p=0,f=0;
      const c = async (n_, fn_) => { try { await fn_(); p++; } catch(e){ f++; } };
      await c('x', async () => { await Promise.resolve(); throw new Error('boom'); });
      assert.strictEqual(f, 1, '非同步失敗沒被算成 fail'); });
    console.log('harness 自我陽性對照（沒這一組，全綠不代表測到東西）');
    await check('check 抓得到同步失敗', () => assert.strictEqual(syncCaught, 'no-throw'));
    await check('🔴 check 抓得到 async 測試體在 await 之後丟的錯（舊版會報成通過）', () => assert.strictEqual(asyncCaught, 'no-throw'));
    await check('🔴 check 本體是 async function——改回同步版此條必轉紅', () => {
      assert.strictEqual(check.constructor.name, 'AsyncFunction',
        'check 不是 async function ⇒ 它不會 await 測試體，async 斷言全部是空的');
    });
  }

  console.log('\nexports 有校正函式');
  await check('calibParseTable／calibGenLadder／dualLadderCalibrated／buildCalibStrip 皆匯出', () => {
    for (const k of ['calibParseTable','calibLookupLin','calibMatches','calibGenLadder','dualLadderCalibrated','buildCalibStrip','buildCalibStripParts','calibStripDefaultS','calibStripGeo'])
      assert(typeof E[k] === 'function', k + ' 缺');
  });

  console.log('\n保命索：calib 缺席 ⇒ 與舊路徑逐值相同');
  const slotsWG = [{ color: '#F2F0EB' }, { color: '#5D6268' }];
  await check('dualLadderCalibrated(null) 的 t／LA／LB 與 dualLadder 逐值相同', () => {
    const a = E.dualLadder(slotsWG[0].color, slotsWG[1].color, 8);
    const b = E.dualLadderCalibrated(slotsWG, 8, null);
    assert.deepStrictEqual(b.t, a.t); assert.strictEqual(b.LA, a.LA); assert.strictEqual(b.LB, a.LB);
    assert.strictEqual(b.calib.present, false); assert.strictEqual(b.lookupLin, undefined);
  });
  await check('quantizeDual：slots 不帶 calib ⇒ 回傳無 calib 鍵、標籤與 palette 與理論梯相同', async () => {
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
    await check('白×藍 8 階：100/84/69/55/40/26/13/0 → 100/75/61/43/37/31/16/0（R8-5 原紀錄）', () => {
      const theory = E.dualLadder('#F2F0EB', '#93D9FA', 8).t.map(pct);
      assert.deepStrictEqual(theory, [100,84,69,55,40,26,13,0], '理論階梯要先對得上 R8-5 的紀錄');
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: blue, apply: true });
      assert.strictEqual(lad.calib.applied, true, lad.calib.why);
      assert.deepStrictEqual(lad.t.map(pct), [100,75,61,43,37,31,16,0]);
      assert(Math.abs(lad.calib.span - 11.3) < 0.3, 'span≈11.3 L*，得 ' + lad.calib.span);
    });
    await check('quantizeDual 帶 calib ⇒ palette 的 t＝校正梯、lin＝實測色（④-1）、回傳 calib 狀態', async () => {
      const img = fakeImg();
      const slots = slotsBlue.map(s => ({ ...s })); slots[0].calib = { table: blue, apply: true };
      const q = await E._internals.quantizeDual(img, { klevels: 8 }, slots, null);
      assert.strictEqual(q.calib.applied, true);
      assert.deepStrictEqual(q.palette.map(p => pct(p.t)), [100,75,61,43,37,31,16,0]);
      const p0 = q.palette[0], p7 = q.palette[7];
      assert.deepStrictEqual(p0.lin, E.calibLookupLin(E.calibParseTable(blue), 1));
      assert.deepStrictEqual(p7.lin, E.calibLookupLin(E.calibParseTable(blue), 0));
    });
    await check('apply:false ⇒ 不動 t（理論梯），但 lookupLin 存在（只做 ④-1 顯示）', () => {
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: blue, apply: false });
      assert.strictEqual(lad.calib.applied, false); assert.strictEqual(lad.calib.matches, true);
      assert.deepStrictEqual(lad.t.map(pct), [100,84,69,55,40,26,13,0]);
      assert(typeof lad.lookupLin === 'function');
    });
    await check('料色不符 ⇒ 不套用、無 lookupLin、why 講清楚', () => {
      const lad = E.dualLadderCalibrated(slotsWG, 8, { table: blue, apply: true });
      assert.strictEqual(lad.calib.present, true); assert.strictEqual(lad.calib.matches, false);
      assert.strictEqual(lad.calib.applied, false); assert(lad.calib.why.includes('不符'));
      assert.strictEqual(lad.lookupLin, undefined);
      assert.deepStrictEqual(lad.t, E.dualLadder(slotsWG[0].color, slotsWG[1].color, 8).t);
    });
    await check('白×黃（L* 跨幅 4.6 < 8）⇒ 護欄③擋下：applied=false、t＝理論梯、why 含「跨幅」', () => {
      const slotsY = [{ color: '#F2F0EB' }, { color: '#FBE534' }];
      const lad = E.dualLadderCalibrated(slotsY, 8, { table: yellow, apply: true });
      assert.strictEqual(lad.calib.matches, true);
      assert.strictEqual(lad.calib.applied, false);
      assert(lad.calib.why.includes('跨幅'), lad.calib.why);
      assert.deepStrictEqual(lad.t, E.dualLadder(slotsY[0].color, slotsY[1].color, 8).t);
    });
    await check('壞表 ⇒ present 但 why 說讀不到、不丟例外', () => {
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: { 料數: 4 }, apply: true });
      assert.strictEqual(lad.calib.present, true); assert.strictEqual(lad.calib.applied, false);
      assert(lad.calib.why.includes('讀不到'));
    });
    await check('非單調表 ⇒ 護欄④擋下', () => {
      const bad = JSON.parse(JSON.stringify(blue));
      bad['量測'][3]['量到色'] = '#F2F0EB';   // 中段突然回到純白＝非單調
      const lad = E.dualLadderCalibrated(slotsBlue, 8, { table: bad, apply: true });
      assert.strictEqual(lad.calib.applied, false); assert(lad.calib.why.includes('單調'));
    });
  }

  console.log('\n校正片（直立條）產生器');
  await check('calibStripDefaultS：料A 較亮 ⇒ 白端加密；料A 較暗 ⇒ 鏡射到 S≈0 端', () => {
    assert.deepStrictEqual(E.calibStripDefaultS('#F2F0EB', '#5D6268'), [1,0.94,0.87,0.78,0.67,0.53,0.35,0]);
    assert.deepStrictEqual(E.calibStripDefaultS('#5D6268', '#F2F0EB'), [1,0.65,0.47,0.33,0.22,0.13,0.06,0]);
  });
  await check('buildCalibStripParts 預設＝v2c 洗料柱版幾何（40×6×16、每階 2 mm、柱 12／gap 8＝0914 實印 12m03s 那條）', () => {
    /* v1（80×8×48、每階 6 mm、無柱、實印 32m45s）已作廢：Eric 0914 裁「建議還是使用洗料塔」＋「不要印那麼久」。
       幾何的唯一來源＝engine.js 的 CALIB_STRIP_GEO；頁面不得再自己寫一份（v1／v2c 分叉就是那樣來的）。 */
    assert.deepStrictEqual(E.calibStripGeo(), { widthMm: 40, thickMm: 6, bandMm: 2, purgeMm: 12, purgeGapMm: 8, purgeWalls: 2 });
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰' });
    assert.strictEqual(c.width, 40); assert.strictEqual(c.thick, 6);
    assert.strictEqual(c.band, 2);   assert.strictEqual(c.height, 16);      // 8 階 × 2 mm
    assert.strictEqual(c.purge, 12); assert.strictEqual(c.purgeGap, 8); assert.strictEqual(c.purgeWalls, 2);
  });
  await check('buildCalibStripParts：8 片＋8 柱、片名 S1／…／S0、柱名「洗料柱NN … S…」、只有片的正／背面禁縫', () => {
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
  await check('🔴 柱段與片段的 extruder 逐階相同（同一個 M6051 配方，柱才洗得到那一階的殘料）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268' });
    const objs = [...c.cfg.matchAll(/<object id="(\d+)">([\s\S]*?)<\/object>/g)]
      .map(m => ({ id: m[1], ex: [...m[2].matchAll(/key="extruder" value="(\d+)"/g)].map(x => Number(x[1])) }));
    const tower = objs.find(o => o.id === '2000'), strip = objs.find(o => o.id === '1000');
    assert(tower && strip, 'cfg 要有 2000（柱）與 1000（片）兩顆物件，實得 ' + objs.map(o => o.id).join(','));
    assert.deepStrictEqual(strip.ex, [1, 2, 3, 4, 5, 6, 7, 8]);
    assert.deepStrictEqual(tower.ex, strip.ex);   // 不同＝柱洗的是別階的料，整條校正片作廢
  });
  await check('柱的 build item 排在片之前（切片器逐層先印柱）＋「片＋柱」整組置中（3MF 座標＝G-code 座標）', () => {
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
  await check('與 python 參考正本 make_calib_3mf.py v2c 產物逐位元組相同（3dmodel.model 的 sha256）', () => {
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
  await check('purgeMm:0 ⇒ 退回無柱幾何（只給離線對照用；build item 剩一個、仍置中）', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', purgeMm: 0, widthMm: 80, thickMm: 8, bandMm: 6 });
    assert.strictEqual(c.height, 48);
    assert.strictEqual(c.purgeBox, null);
    assert.strictEqual((c.model.match(/<item /g) || []).length, 1);
    assert(!/洗料柱/.test(c.cfg));
  });
  await check('buildCalibStrip：makeZip 出 Blob，5 個 entry，體積 >2 KB', async () => {
    const r = await E.buildCalibStrip({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰' });
    assert(r.blob && r.blob.size > 2000, 'blob 太小 ' + (r.blob && r.blob.size));
    const bytes = new Uint8Array(await r.blob.arrayBuffer());
    let cnt = 0; for (let i = 0; i + 4 <= bytes.length; i++) if (bytes[i]===0x50&&bytes[i+1]===0x4b&&bytes[i+2]===0x03&&bytes[i+3]===0x04) cnt++;
    assert.strictEqual(cnt, 5);
  });
  await check('端點不是純色 ⇒ 拒產', () => {
    assert.throws(() => E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', s: [0.9, 0.5, 0] }), /純色錨點/);
  });

  console.log('\n兩頁的 S 清單只有一個來源（0915 牌 c-0915-PTI-03；§S-10「頁面功能要有存在性斷言才算有守衛」）');
  const WEB = path.join(__dirname, '..', '..', 'resources', 'web', 'phototile');
  const calHtml = fs.readFileSync(path.join(WEB, 'calibration.html'), 'utf8');
  const idxHtml = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  const LADDER = '1,0.94,0.87,0.78,0.67,0.53,0.35,0';
  await check('calibration.html 載 engine.js 並用 calibStripDefaultS 算 S（不自己寫一份）', () => {
    assert(/<script src="engine\.js"><\/script>/.test(calHtml), '沒有載 engine.js');
    assert(calHtml.includes('calibStripDefaultS'), '沒有呼叫 calibStripDefaultS');
    assert(/function\s+syncVsList\s*\(/.test(calHtml), '沒有 syncVsList（料色改了要重算）');
  });
  await check('🔴 calibration.html 不得把階梯寫死當預設值（料A 較暗時引擎會鏡射，寫死的不會跟著動＝靜默錯表）', () => {
    /* 0915 實錄：舊版 <input id="vsList" value="1,0.94,…">，而引擎在 L(A)<L(B) 時回 1,0.65,…
       ⇒ 使用者沒手抄就拿錯的鍵去量，整張表歪掉而且不報錯。這條就是防它長回來。 */
    assert(!new RegExp('id="vsList"[^>]*value="' + LADDER.replace(/\./g, '\\.')).test(calHtml),
           'vsList 又出現寫死的預設階梯');
    assert.deepStrictEqual(E.calibStripDefaultS('#5D6268', '#F2F0EB'), [1,0.65,0.47,0.33,0.22,0.13,0.06,0]);
  });
  await check('index.html 第 3 步不再叫使用者手抄 S 清單、也不再叫他填料色', () => {
    assert(!idxHtml.includes('各階 S 照上面'), '手抄指示還在');
    /* 0915 dcf45dc9fc 之後料色是從照片直接量的（autoSlot 預設 checked）⇒ 這句指示會誤導。 */
    assert(!idxHtml.includes('把上面那兩個料色填進去'), '叫使用者填料色的指示還在');
    assert(/各階 S (會自動算出來，不用抄|也會自動算)/.test(idxHtml), '沒有講「自動算」');
  });

  console.log('\n校正回讀・工作室內覆蓋層（0915 牌 c-0915-PTI-06；Eric「不用外部瀏覽器」）');
  await check('工作室有覆蓋層入口，iframe 指向 calibration.html?embedded=1', () => {
    assert(idxHtml.includes('btnCalibOverlay'), '沒有覆蓋層入口鈕');
    assert(idxHtml.includes("calibration.html?embedded=1"), 'iframe 沒有帶 embedded=1');
  });
  await check('🔴 套表只有一個入口：檔案匯入與覆蓋層帶回都走 calibAcceptRaw；料槽只有一個寫入點（段 F＝ptMatApply）', () => {
    assert(idxHtml.includes('function calibAcceptRaw'), '沒有抽出單一入口');
    /* 0914 Q2 乙「匯入時把料色回填成表的料色」在段 F（R6-16 料→圖，牌 c-0923-ACC-23）換成
       「新量的那組直接成為產圖流程的選擇」，料色一律從材料庫選的那組寫進料槽。
       寫入點只能有一個——這條線已被兩份實作咬過三次（第二份遲早漂移）。註解裡提到的不算。 */
    const writersIn = src => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '')
      .split(/\r?\n/).filter(l => /slots\[[^\]]*\](\.color)?\s*=[^=]/.test(l)).map(l => l.trim());
    const w = writersIn(idxHtml);
    assert.strictEqual(w.length, 1, '料槽寫入點 ' + w.length + ' 處：' + w.join(' ｜ '));
    assert(/inf\.colors\.forEach/.test(w[0]), '唯一的寫入點不是 ptMatApply 那一行：' + w[0]);
    // 陽性對照：把 0914 那行料色回填放回 calibAcceptRaw，守衛必須數到 2
    const mutated = idxHtml.replace('      const quad=Array.isArray(tbl.pairs);', "      const quad=Array.isArray(tbl.pairs); slots[0].color=tbl.slots[0].toLowerCase();");
    assert(mutated !== idxHtml, '陽性對照沒改到東西（錨點失效）');
    assert.strictEqual(writersIn(mutated).length, 2, '守衛數不到被放回去的第二個寫入點');
  });
  await check('calibration.html 有 EMBEDDED 判定與 postToStudio，且非內嵌時行為不變', () => {
    assert(calHtml.includes('const EMBEDDED'), '沒有 EMBEDDED 判定');
    assert(calHtml.includes('function postToStudio'), '沒有 postToStudio');
    assert(calHtml.includes("embedded')==='1'") && calHtml.includes('window.parent!==window'),
      'EMBEDDED 沒有同時要求參數與真的在 iframe 裡');
    /* ⚠ 不做跨行比對（行尾 CRLF/LF 差異會讓斷言假紅——本棒第一版就是這樣紅的）。 */
    assert(calHtml.includes("a.download='色彩校正表.json'"), '非內嵌路徑的下載行為被改掉了');
    assert((calHtml.match(/saveAsFile\(\)/g) || []).length >= 2,
      'saveAsFile 應在「fallback」與「非內嵌」兩條路徑各呼叫一次');
  });
  await check('🔴 覆蓋層有明確回程（MainFrame.cpp 當初不做內嵌的理由就是「校正頁沒有回程」）', () => {
    assert(calHtml.includes('btnBackStudio'), '沒有取消返回鈕');
    assert(calHtml.includes('phototile_calib_cancel'), '沒有取消訊息');
    assert(idxHtml.includes("d.type==='phototile_calib_cancel'"), '工作室沒有處理取消');
    assert(/x\.textContent='關閉'/.test(idxHtml), '覆蓋層工具列沒有關閉鈕');
    assert(idxHtml.includes("e.key==='Escape'"), 'Esc 關不掉覆蓋層');
  });
  await check('🔴 帶回失敗有 fail-loud 退路：等不到 ack 就存檔並講出來', () => {
    assert(calHtml.includes('phototile_calib_ack'), '校正頁沒有等 ack');
    assert(idxHtml.includes('phototile_calib_ack'), '工作室沒有回 ack');
    assert(calHtml.includes('工作室沒有回應'), '沒有 fail-loud 訊息');
  });
  await check('🔴 工作室 close 排到下一個 task，否則 ack 送不到（本棒實測抓到 ack=false）', () => {
    assert(idxHtml.includes('setTimeout(close, 0)'),
      'close 若與 ack 同一個 tick，iframe 會在收到 ack 前被移除 ⇒ 校正頁誤報「工作室沒有回應」');
  });
  await check('只收自己那個 iframe 的訊息（file:// 的 origin 是 "null"，比 origin 沒有意義）', () => {
    assert(idxHtml.includes('e.source!==frame.contentWindow'), '沒有比對訊息來源');
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
  await check('套表、不開 toneMap ⇒ 圖裡 L*45 的灰與 L*5 的黑都夾成最深階（中間階空）', async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: true };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    const h = hist(q); assert.strictEqual(h[1] || 0, 0, '中間階應為空'); assert(h[0] > 0 && h[2] > 0);
    assert.strictEqual(q.calib.toneMap, undefined);
  });
  await check("套表＋toneMap:'stretch' ⇒ 三階都有像素（各三分之一），calib.toneMap 記錄映射範圍", async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: true, toneMap: 'stretch' };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    const h = hist(q); assert(h[0] > 0 && h[1] > 0 && h[2] > 0, JSON.stringify(h));
    assert.strictEqual(h[0], h[1]); assert.strictEqual(h[1], h[2]);
    assert.strictEqual(q.calib.toneMap.mode, 'stretch'); assert(q.calib.toneMap.Lmin <= 5.5 && q.calib.toneMap.Lmax >= 94.5);
  });
  await check("apply:false＋toneMap:'stretch' ⇒ 不映射（映射只跟著 ④-2 走）", async () => {
    const slots = slotsGray.map(s => ({ ...s })); slots[0].calib = { table: tableGray, apply: false, toneMap: 'stretch' };
    const q = await E._internals.quantizeDual(triImg(), { klevels: 3 }, slots, null);
    assert.strictEqual(q.calib.toneMap, undefined);
  });
  await check('toneStretch 本身：百分位夾住、映射到 [dark, light] 兩端', () => {
    const im = triImg(); const ts = E.toneStretch(im.lab, im.w * im.h, 95, 48.3, {});
    assert(Math.abs(ts.mapL(5) - 48.3) < 1e-6 && Math.abs(ts.mapL(95) - 95) < 1e-6);
    assert(ts.mapL(45) > 60 && ts.mapL(45) < 80, 'L*45 應落在中段（得 ' + ts.mapL(45) + '）');
  });


  /* ═══════════════ 段 A｜材料庫（R6-14；牌 c-0922-ACC-15） ═══════════════ */
  console.log('\n段 A｜材料庫：身分、pair、失效範圍、遷移、儲存轉接層');
  const mat = (fid, label, hex) => ({ fid, label, hex });
  const WHITE = mat('GPINGPLA', '白 210', '#F2F0EB');
  const GRAY  = mat('GPINGPLA', '深灰 210', '#5D6268');
  const RED   = mat('GPINGABS', '紅', '#C0392B');
  const BLUE2 = mat('GPINGABS', '藍', '#2E86C1');
  const mkPts = n_ => Array.from({ length: n_ }, (_, i) => ({ S: 1 - i / (n_ - 1), hex: '#' + (16 + i * 12).toString(16).padStart(2,'0').repeat(3).toUpperCase() }));
  const mkPair = (a, b) => ({ a, b, kind: M.KINDS.DUAL, pts: mkPts(8), source: 'readback', measuredAt: '2026-09-14' });

  await check('matlib 匯出齊全（schema／讀寫／遷移／轉接層）', () => {
    for (const k of ['matKey','pairId','emptyLib','normalize','upsertPair','findPair','listMaterials',
                     'partnersOf','dropMaterial','pairFromDual','pairsFromQuad','toCalibTable',
                     'toQuadCalibTable','migrateLegacy','needsClaim','claimPair','load','save',
                     'readLegacyRaw','setStorage','memoryStorage','nullStorage'])
      assert(typeof M[k] === 'function', k + ' 缺');
    assert.strictEqual(M.SCHEMA, 1);
    assert.strictEqual(M.LEGACY_KEY, 'ping_phototile_calib_dual_v1');
  });

  await check('🔴 pair id 與端點順序無關（R6-4 的失效單位就是 pair，「A 配 B」不該變成兩筆）', () => {
    assert.strictEqual(M.pairId(WHITE, GRAY), M.pairId(GRAY, WHITE));
    assert.notStrictEqual(M.pairId(WHITE, GRAY), M.pairId(WHITE, RED));
  });
  await check('🔴 hex 不進 key（R6-14 子題 1：同一支料不同批量到的值會不一樣）', () => {
    assert.strictEqual(M.matKey(mat('GPINGPLA','白 210','#F2F0EB')),
                       M.matKey(mat('GPINGPLA','白 210','#EFEDE8')));
    /* 陽性對照：fid 或標籤不同就必須是別支料——一個 preset ≠ 一捷料 */
    assert.notStrictEqual(M.matKey(WHITE), M.matKey(mat('GPINGPLA','黑 210','#F2F0EB')));
    assert.notStrictEqual(M.matKey(WHITE), M.matKey(mat('GPINGABS','白 210','#F2F0EB')));
  });

  await check('同一對重量測 ⇒ 取代不新增（而且原位取代，清單不跳動）', () => {
    const lib = M.emptyLib();
    M.upsertPair(lib, mkPair(WHITE, GRAY));
    M.upsertPair(lib, mkPair(WHITE, RED));
    const again = mkPair(GRAY, WHITE); again.pts = mkPts(5); again.measuredAt = '2026-09-22';
    M.upsertPair(lib, again);
    assert.strictEqual(lib.pairs.length, 2, '測到重複新增');
    assert.strictEqual(lib.pairs[0].pts.length, 5, '沒取代成新的那一筆');
    assert.strictEqual(lib.pairs[0].measuredAt, '2026-09-22');
    assert.strictEqual(M.findPair(lib, WHITE, RED).pts.length, 8, '另一對被動到了');
  });

  await check('🔴 R6-4 逐字：換掉 B ⇒ 只有含 B 的三組失效，A/C、A/D、C/D 保留不重測', () => {
    const A = WHITE, B = GRAY, C = RED, D = BLUE2;
    const lib = M.emptyLib();
    [[A,B],[A,C],[A,D],[B,C],[B,D],[C,D]].forEach(([x,y]) => M.upsertPair(lib, mkPair(x,y)));
    assert.strictEqual(lib.pairs.length, 6);
    const r = M.dropMaterial(lib, B);
    assert.strictEqual(r.removed.length, 3, '失效的不是三組（得 ' + r.removed.length + '）');
    assert.strictEqual(r.kept.length, 3, '保留的不是三組（得 ' + r.kept.length + '）');
    for (const [x,y] of [[A,C],[A,D],[C,D]]) assert(M.findPair(lib, x, y), '不含 B 的那一對被誤刪：' + M.pairId(x,y));
    for (const [x,y] of [[A,B],[B,C],[B,D]]) assert(!M.findPair(lib, x, y), '含 B 的那一對沒被刪：' + M.pairId(x,y));
    /* 陽性對照：料的清單是從 pair 端點推出來的（子題 3）⇒ B 隨著消失，其餘三支還在 */
    const keys = M.listMaterials(lib).map(x => x.key);
    assert(!keys.includes(M.matKey(B)), 'B 還在料清單裡');
    assert.strictEqual(keys.length, 3);
  });

  await check('舊鍵 → 新庫的遷移：逐欄斷言（fid 空、標籤帶原 hex、source legacy-hex、量測點原樣）', () => {
    const lib = M.emptyLib();
    const tbl = E.calibParseTable(TABLE_BLUE);
    const r = M.migrateLegacy(lib, tbl, { measuredAt: '2026-09-14' });
    assert.strictEqual(r.added, true, r.why);
    const p = lib.pairs[0];
    assert.strictEqual(p.a.fid, null, '舊表沒有 filament_id，不該憑空填一個');
    assert.strictEqual(p.b.fid, null);
    assert.strictEqual(p.a.label, '#F2F0EB'); assert.strictEqual(p.a.hex, '#F2F0EB');
    assert.strictEqual(p.b.label, '#93D9FA'); assert.strictEqual(p.b.hex, '#93D9FA');
    assert.strictEqual(p.source, 'legacy-hex');
    assert.strictEqual(p.measuredAt, '2026-09-14');
    assert.deepStrictEqual(p.pts.map(x => x.S), tbl.pts.map(x => x.S));
    assert.deepStrictEqual(p.pts.map(x => x.hex), tbl.pts.map(x => x.hex));
    assert.strictEqual(M.needsClaim(p), true, '遷進來的那一格要請使用者認領（子題 2 附款）');
  });
  await check('遷移是冪等的，而且**不覆蓋**庫裡已有的那一筆（否則把後來重量的資料丟了）', () => {
    const lib = M.emptyLib();
    const tbl = E.calibParseTable(TABLE_BLUE);
    M.migrateLegacy(lib, tbl, {});
    lib.pairs[0].pts = mkPts(3);                       // 假裝使用者後來又量了一次
    const r2 = M.migrateLegacy(lib, tbl, {});
    assert.strictEqual(r2.added, false, '第二次遷移又加了一筆');
    assert.strictEqual(lib.pairs.length, 1);
    assert.strictEqual(lib.pairs[0].pts.length, 3, '被舊資料蓋回去了');
  });
  await check('🔴 舊鍵不刪（rollback 的唯一退路）——matlib 裡沒有任何一行動得了舊鍵', () => {
    assert(/readLegacy/.test(ML_SRC), 'matlib 根本沒讀舊鍵');
    assert(!/removeItem\s*\(\s*LEGACY_KEY/.test(ML_SRC), 'matlib 裡有刪舊鍵的碼');
    assert(!/writeLegacy|setItem\s*\(\s*LEGACY_KEY/.test(ML_SRC), '庫存在之後不該再寫舊鍵');
  });
  await check('認領：身分換了 ⇒ id 跟著換，量測點與出身（legacy-hex）保留', () => {
    const lib = M.emptyLib();
    M.migrateLegacy(lib, E.calibParseTable(TABLE_BLUE), {});
    const before = lib.pairs[0];
    const pts0 = before.pts.slice();
    const after = M.claimPair(lib, before.id, { fid:'GPINGPLA', label:'白 210' }, { fid:'GPINGPLA', label:'淡藍 210' }, { claimedAt:'2026-09-22' });
    assert.strictEqual(lib.pairs.length, 1, '認領完變成兩筆');
    assert.notStrictEqual(after.id, before.id, 'id 沒跟著身分改');
    assert.deepStrictEqual(after.pts, pts0, '量測點被動到了');
    assert.strictEqual(after.source, 'legacy-hex', '出身要可追溯，不因為認領就變乾淨');
    assert.strictEqual(after.claimedAt, '2026-09-22');
    assert.strictEqual(M.needsClaim(after), false);
  });

  await check('儲存轉接層：暫存往返，而且 normalize 會丟掉壞筆、不整份作廢', () => {
    const st = M.memoryStorage(); M.setStorage(st);
    const lib = M.emptyLib(); M.upsertPair(lib, mkPair(WHITE, GRAY));
    assert.deepStrictEqual(M.save(lib), { persisted: true, why: '' });
    assert.strictEqual(M.load().pairs.length, 1);
    st.writeLib(JSON.stringify({ schema: 1, pairs: [
      { a: WHITE, b: GRAY, pts: [{ S: 1, hex: '#FFFFFF' }, { S: 0, hex: '#000000' }] },
      { a: WHITE, b: RED, pts: [{ S: 1, hex: 'not-a-hex' }] },
      { a: null, b: RED, pts: [] } ] }));
    assert.strictEqual(M.load().pairs.length, 1, '壞筆沒被丟掉，或好筆被連坐');
  });
  await check('🔴 存不進去要**講出來**，不靜默（既有 calibTable.persisted 同一紀律）', () => {
    M.setStorage(M.nullStorage('測試：這個環境不可寫'));
    const r = M.save(M.emptyLib());
    assert.strictEqual(r.persisted, false);
    assert(/不可寫/.test(r.why), 'why 沒講出真正的原因：' + r.why);
    assert.deepStrictEqual(M.load(), M.emptyLib(), '寫不進去時讀應該還是能跑（回空庫）');
    M.setStorage(M.memoryStorage());
  });

  await check('庫 → 校正表往返：toCalibTable 吐出來的形狀，引擎 calibParseTable 吃得下且值逐格相同', () => {
    const src = E.calibParseTable(TABLE_BLUE);
    const pair = M.pairFromDual(src, { materials: [WHITE, BLUE2] });
    const back = E.calibParseTable(M.toCalibTable(pair));
    assert.deepStrictEqual(back.pts.map(p => p.S), src.pts.map(p => p.S));
    assert.deepStrictEqual(back.pts.map(p => p.hex), src.pts.map(p => p.hex));
    assert.deepStrictEqual(back.slots.slice(0,2), ['#F2F0EB', '#2E86C1'], '料色要跟著庫裡的料走');
  });
  await check('🔴 四料湊表：pair 存的方向跟要求的方向相反時，S 要翻回來（不翻＝整對曲線頭尾顛倒的靜默錯表）', () => {
    const lib = M.emptyLib();
    M.upsertPair(lib, { a: GRAY, b: WHITE, kind: M.KINDS.QUAD,   // 存的是（灰, 白）
      pts: [{ S: 1, hex: '#5D6268' }, { S: 0, hex: '#F2F0EB' }], source: 'readback' });
    const r = M.toQuadCalibTable(lib, [WHITE, GRAY, RED, BLUE2]);   // 要的是（白=A, 灰=B）
    const rows = r.table['量測'].filter(x => /^R1C/.test(x['格']));
    assert.strictEqual(rows.length, 2);
    const byHex = Object.fromEntries(rows.map(x => [x['量到色'], x['配方']]));
    assert.deepStrictEqual(byHex['#F2F0EB'], { A: 100, B: 0, C: 0, D: 0 }, '白的純色格應該是 A=100');
    assert.deepStrictEqual(byHex['#5D6268'], { A: 0, B: 100, C: 0, D: 0 }, '灰的純色格應該是 B=100');
  });
  await check('🔴 湊不齊的那幾對列在 missing，**不補理論值**（R6-16）', () => {
    const lib = M.emptyLib();
    M.upsertPair(lib, mkPair(WHITE, GRAY));
    const r = M.toQuadCalibTable(lib, [WHITE, GRAY, RED, BLUE2]);
    assert.strictEqual(r.present.length, 1);
    assert.strictEqual(r.missing.length, 5);
    assert.strictEqual(r.table['量測'].length, 8, '湊不到的對被補了資料進去');
    assert.deepStrictEqual(r.missing.map(x => x.row), [2,3,4,5,6]);
  });

  /* ═══════════════ 段 C｜四料 48 格端到端 ═══════════════ */
  console.log('\n段 C-1｜48 格校正塊產生器（A 案；R6-2 附款／R6-6）');
  const QCOL = ['#F2F0EB', '#C0392B', '#2E86C1', '#1A1A1A'];
  const QNAME = ['白', '紅', '藍', '黑'];
  await check('🔴 與 python 參考正本 make_calib_quad_3mf.py 產物逐位元組相同（3dmodel.model 與 model_settings.config 的 sha256）', () => {
    const c = E.buildCalibQuadParts({ colors: QCOL, names: QNAME });
    const h = x => require('crypto').createHash('sha256').update(x, 'utf8').digest('hex');
    /* 這兩顆值的來源＝根 repo 照片磚_色彩校正/色彩校正_四料48格.3mf（make_calib_quad_3mf.py 預設參數產出、
       附自我驗證 49 支全過）。🔴 要改這兩顆值之前先回答一句：新幾何實印驗證過了嗎？
       沒有就不要改它，要改的是程式。 */
    assert.strictEqual(h(c.model), '685ed37e8626bf17abce6478017da630042ebbe3e80016fa064c77617972ff38', '3dmodel.model 不同');
    assert.strictEqual(h(c.cfg),   '086a100d10fdd0ad6e0da221759eea39f92aca1bd775a36b320d41868b4cf110', 'model_settings.config 不同');
  });
  await check('48 格（6 對 × 8 階）＋洗料柱＝49 支；正面 80×60、厚 10 mm（Orca 上限 64）', () => {
    const c = E.buildCalibQuadParts({ colors: QCOL, names: QNAME });
    assert.strictEqual(c.cells, 48); assert.strictEqual(c.partCount, 49);
    assert.strictEqual(c.width, 80); assert.strictEqual(c.height, 60); assert.strictEqual(c.thick, 10);
    assert(c.partCount <= 64, '超過 Orca 零件上限');
  });
  await check('🔴 零件名符合 C++ parse_photo_part_name：尾端 A B C D 四個 token、和＝100、有 #RRGGBB', () => {
    const c = E.buildCalibQuadParts({ colors: QCOL, names: QNAME });
    const names = [...c.cfg.matchAll(/<metadata key="name" value="([^"]+)"\/>/g)].map(m => m[1]).slice(1);
    assert.strictEqual(names.length, 49);
    for (const nm of names){
      const tk = nm.split(' ');
      assert(tk.length >= 5, 'token 不足 5 個：' + nm);
      const tail = tk.slice(-4);
      assert(/^A\d+$/.test(tail[0]) && /^B\d+$/.test(tail[1]) && /^C\d+$/.test(tail[2]) && /^D\d+$/.test(tail[3]), nm);
      assert.strictEqual(tail.reduce((s_, t) => s_ + parseInt(t.slice(1), 10), 0), 100, nm);
      assert(/#[0-9A-F]{6}/.test(nm), '沒有預覽色：' + nm);
    }
  });
  await check('整組（磚＋洗料柱）置中在原點 ⇒ 3MF 座標＝G-code 座標（0914 v2 實切踩過）', () => {
    const c = E.buildCalibQuadParts({ colors: QCOL, names: QNAME });
    /* 聯集 X 範圍 [0, 80+15+25=120] ⇒ 要平移 -60；Y [0,10] ⇒ -5 */
    assert(c.model.includes('transform="1 0 0 0 1 0 0 0 1 -60 -5 0"'), '未置中，或置中時沒含洗料柱');
  });
  await check('pillarMm:0 ⇒ 退回無柱幾何（48 支）；料色不合法 ⇒ 拒產（陽性對照）', () => {
    const c = E.buildCalibQuadParts({ colors: QCOL, names: QNAME, pillarMm: 0 });
    assert.strictEqual(c.partCount, 48);
    assert(c.model.includes('transform="1 0 0 0 1 0 0 0 1 -40 -5 0"'), '無柱時該以 80 置中');
    assert.throws(() => E.buildCalibQuadParts({ colors: ['#F2F0EB','#C0392B','不是色','#1A1A1A'] }));
    assert.throws(() => E.buildCalibQuadParts({ colors: ['#F2F0EB','#C0392B'] }));
  });
  await check('🔴 R6-8：產生器的階段比例與 quantizeQuad 實際會吐的逐字相同', () => {
    for (const K of [2,4,6,8]){
      const mine = E.calibQuadSteps(K);
      const engineWay = Array.from({ length: K }, (_, s_) => Math.round((1 - s_/(K-1)) * 100));
      assert.deepStrictEqual(mine, engineWay, 'K=' + K);
    }
    assert.deepStrictEqual(E.calibQuadSteps(8), [100,86,71,57,43,29,14,0]);
  });

  console.log('\n段 C-2｜四料表匯入（calibParseTable 依料數分派）');
  /* 合成一份「量測表」：直接拿 48 格產生器的配方表（與離線參考正本同構），
     量到色預設就用那一格的理論預覽色 ⇒ 「量到的＝理論的」的理想案，反解必須得回原 S。 */
  function quadTable(opt){
    opt = opt || {};
    const c = E.buildCalibQuadParts({ colors: opt.colors || QCOL, names: QNAME });
    const rows = [];
    const re = /校正R(\d+)C(\d+) (#[0-9A-F]{6}) A(\d+) B(\d+) C(\d+) D(\d+)/g;
    let m;
    while ((m = re.exec(c.cfg))){
      const r = +m[1], col = +m[2];
      if (opt.dropRow && opt.dropRow === r) continue;
      rows.push({ '格': 'R' + r + 'C' + col,
                  '配方': { A:+m[4], B:+m[5], C:+m[6], D:+m[7] },
                  '量到色': opt.tweak ? opt.tweak(m[3], r, col) : m[3] });
    }
    return { '格式': '測試合成', '校正塊種類': '四料 48 格（6 對 × 8 階）', '料數': 4,
             '料': (opt.colors || QCOL).map((h, i) => ({ 槽:'ABCD'[i], 色:h, 名:QNAME[i] })),
             '量測': rows };
  }
  await check('料數 4 ⇒ calibParseTable 分派給 quad；6 對 × 8 點，對序照 R6-2', () => {
    const t = E.calibParseTable(quadTable());
    assert(Array.isArray(t.pairs), '沒走到 quad 分支');
    assert.strictEqual(t.pairs.length, 6);
    assert.deepStrictEqual(t.pairs.map(p => [p.i, p.j]), [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]]);
    t.pairs.forEach(p => assert.strictEqual(p.pts.length, 8, p.i + ',' + p.j));
    assert.deepStrictEqual(t.slots, QCOL);
  });
  await check('🔴 正向 oracle：六對各自反解得回原 S（100/86/71/57/43/29/14/0）', () => {
    const t = E.calibParseTable(quadTable());
    const want = E.calibQuadSteps(8).map(w => w / 100);
    t.pairs.forEach(p => assert.deepStrictEqual(p.pts.map(x => x.S), want, '對 ' + p.i + ',' + p.j));
  });
  await check('🔴 端點純色格只有**一個**非零 ⇒ 不能靠「恰有兩個非零」認對，這裡得全數歸位', () => {
    const t = E.calibParseTable(quadTable());
    const p01 = t.pairs.find(p => p.i === 0 && p.j === 1);
    assert.strictEqual(p01.pts[0].S, 1, 'S=1 那一端（A 純色）沒歸到 A/B');
    assert.strictEqual(p01.pts[7].S, 0, 'S=0 那一端（B 純色）沒歸到 A/B');
    /* 陽性對照：全部 48 格有 6 格是單一非零的純色錨點（每對兩個，共 12 格） */
    const single = quadTable()['量測'].filter(r => ['A','B','C','D'].filter(k => r['配方'][k] > 0).length === 1);
    assert.strictEqual(single.length, 12, '純色錨點格數不對：' + single.length);
  });
  await check('整列缺席（某一對沒量）⇒ 只回 5 對、**不丟例外**（R6-4）', () => {
    const t = E.calibParseTable(quadTable({ dropRow: 2 }));
    assert.strictEqual(t.pairs.length, 5);
    assert(!t.pairs.some(p => p.i === 0 && p.j === 2), 'A/C 還在');
  });
  await check('壞表要丟例外（陽性對照）：用到第三支料／配方不加滿 100／量到色不合法', () => {
    const t1 = quadTable(); t1['量測'][3]['配方'].C = 5; t1['量測'][3]['配方'].A -= 5;
    /* 該列的非零聯集變成三支 ⇒ 列層級那一道會先擋，而且訊息會點名是哪一列。 */
    assert.throws(() => E.calibParseTable(t1), /R1 .*兩支料的混比/);
    const t2 = quadTable(); t2['量測'][0]['配方'].A = 99;
    assert.throws(() => E.calibParseTable(t2), /不是 100/);
    const t3 = quadTable(); t3['量測'][0]['量到色'] = 'nope';
    assert.throws(() => E.calibParseTable(t3), /不合法/);
  });
  await check('🔴 整列只用到**一支**料（非零聯集＝1）也要丟例外——不然 j 是 undefined、曲線算出 NaN 而沒人知道', () => {
    /* 這條是突變檢驗逃出來的缺口：把 `idx.length!==2` 改成 `idx.length>2`，
       原本整套測試竟然全綠——因為合成資料裡每一列聯集都剛好是 2。 */
    const t_ = quadTable();
    t_['量測'].forEach(r => { if (/^R1C/.test(r['格'])) r['配方'] = { A: 100, B: 0, C: 0, D: 0 }; });
    assert.throws(() => E.calibParseTable(t_), /R1 .*兩支料的混比/);
  });
  await check('雙料表餵進雙料路徑不受影響；四料表餵進雙料 ⇒ 講清楚、不崩', () => {
    assert(Array.isArray(E.calibParseTable(TABLE_BLUE).pts), '雙料路徑被動到了');
    const lad = E.dualLadderCalibrated([{ color:'#F2F0EB' }, { color:'#C0392B' }], 8, { table: quadTable(), apply: true });
    assert.strictEqual(lad.calib.applied, false);
    assert(/四料/.test(lad.calib.why), 'why 沒講出是四料表：' + lad.calib.why);
  });

  console.log('\n段 C-3｜四料量化吃實測值（曲線內插；R6-16 不退回理論值）');
  const QSLOTS = () => QCOL.map(c => ({ color: c }));
  function quadImg(){
    const w = 12, h = 12, n_ = w * h;
    const lab = new Float32Array(n_ * 3);
    for (let p = 0; p < n_; p++){
      lab[p*3]   = 4 + (p * 91) / (n_ - 1);
      lab[p*3+1] = -28 + (p % 7) * 9;
      lab[p*3+2] = 34 - (p % 5) * 13;
    }
    return { w, h, lab, lum: new Float32Array(n_), data: new Uint8ClampedArray(n_ * 4) };
  }
  const qdig = q => require('crypto').createHash('sha256').update(Buffer.from(q.rawLabels)).digest('hex');
  /* 🔒 黃金值的來源＝**改動前的 engine.js**（git show HEAD:…）實跑出來的，不是拿新碼自己照的鏡子。
     沒有這一條，改引擎就等於動了所有既有磚的輸出。 */
  const GOLDEN = {
    4: { sha: '47c62f44d10026bbc6f254e2f063e7b484b781a3c614250eb21c887d59b69774', cands: 16 },
    8: { sha: 'c82ea694060733b0161eab006f9a274ba014b456cc6d71cf3bfb081239921a13', cands: 40 },
  };
  await check('🔒 保命索：calib 缺席 ⇒ quantizeQuad 的標籤與 palette **逐位元不變**（K=4／K=8）', async () => {
    for (const K of [4, 8]){
      const q = await E._internals.quantizeQuad(quadImg(), { klevels: K }, QSLOTS(), null);
      assert.strictEqual(qdig(q), GOLDEN[K].sha, 'K=' + K + ' 標籤變了');
      assert.strictEqual(q.candidates, GOLDEN[K].cands, 'K=' + K + ' 候選數變了');
      assert.strictEqual(q.calib, undefined, 'calib 缺席時不該多出 calib 欄位（回傳物形狀要一樣）');
      assert.deepStrictEqual(Object.keys(q), ['rawLabels','palette','dropped','candidates','filterStrategy']);
    }
  });
  await check('🔴 陽性對照：套上**與理論不同**的實測表 ⇒ 標籤必須跟黃金值不同（否則校正根本沒進去）', async () => {
    const dark = quadTable({ tweak: hex => '#' + [0,1,2].map(i => Math.max(0, parseInt(hex.slice(1+i*2, 3+i*2), 16) - 40).toString(16).padStart(2,'0')).join('').toUpperCase() });
    const slots = QSLOTS(); slots[0].calib = { table: dark, apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, true, q.calib.why);
    assert.notStrictEqual(qdig(q), GOLDEN[8].sha, '校正套了等於沒套');
  });
  await check('🔴 候選色拿的是**實測值**（曲線內插），不是理論 mixLin；權重集合維持不變', async () => {
    const t = quadTable();
    const slots = QSLOTS(); slots[0].calib = { table: t, apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, true, q.calib.why);
    assert.strictEqual(q.candidates, GOLDEN[8].cands, '候選數不該因為套表而變');
    /* 量到色就是那一格的 hex ⇒ 每個候選的 lin 要逐值等於 hexLin(量到色)。
       拿 palette 裡任一個權重去表裡找回那一格比對。 */
    const byW = new Map(t['量測'].map(r => [[r['配方'].A, r['配方'].B, r['配方'].C, r['配方'].D].join(','), r['量到色']]));
    let checked = 0;
    for (const p of q.palette){
      const hex = byW.get(p.w.join(','));
      if (!hex) continue;
      const want = hex.slice(1).match(/../g).map(x => Math.pow(parseInt(x,16)/255, 2.2));
      p.lin.forEach((v, i) => assert(Math.abs(v - want[i]) < 1e-12, '候選 ' + p.w.join(',') + ' 的色不是實測值'));
      checked++;
    }
    assert(checked >= 24, '比對到的候選太少（' + checked + '），這條形同虛設');
  });
  await check('🔴 沒有那一對的校正資料 ⇒ **那一對的候選整組消失、不退回理論值**，其餘五對照常（R6-4）', async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable({ dropRow: 2 }), apply: true };   // R2 ≡ A/C
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, true, q.calib.why);
    assert.strictEqual(Object.keys(q.calib.pairs).length, 5);
    assert(!q.calib.pairs['0,2'], 'A/C 還在候選池裡');
    /* A/C 獨有的混比（A>0 且 C>0）一個都不該在⇒ 確實是消失，而不是用理論值頂上 */
    for (const p of q.palette) assert(!(p.w[0] > 0 && p.w[2] > 0), 'A/C 的候選退回了理論值：' + p.w.join(','));
    /* 而 B/D、C/D 這些沒被動到的對要還在 */
    assert(q.palette.some(p => p.w[1] > 0 && p.w[3] > 0), 'B/D 被連坐');
    assert(q.palette.some(p => p.w[2] > 0 && p.w[3] > 0), 'C/D 被連坐');
    assert(q.candidates < GOLDEN[8].cands, '候選數沒減，那一對根本沒被拿掉');
  });
  await check('🔴 護欄：非單調的那一對被擋下（skipped），其餘五對照常', async () => {
    /* 只把 R1（A/B）的中間一格打成比兩端都亮 ⇒ L* 不再單調 */
    const t = quadTable({ tweak: (hex, r, c) => (r === 1 && c === 5) ? '#FFFFFF' : hex });
    const slots = QSLOTS(); slots[0].calib = { table: t, apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(Object.keys(q.calib.pairs).length, 5, JSON.stringify(q.calib.skipped));
    assert(q.calib.skipped.some(x => x.i === 0 && x.j === 1 && /單調/.test(x.why)), JSON.stringify(q.calib.skipped));
  });
  await check('🔴 R6-7 附款：跨幅 4~K 之間**不擋**（只回報 maxLevels）；跨幅 <4 才擋', () => {
    const mk = (lo, hi_) => Array.from({ length: 8 }, (_, i) => {
      const v = Math.round(hi_ - (hi_ - lo) * i / 7);
      const h = v.toString(16).padStart(2,'0').toUpperCase();
      return { S: 1 - i/7, lin: [v/255, v/255, v/255].map(x => Math.pow(x, 2.2)), hex: '#' + h + h + h };
    });
    const wide = E.calibQuadPairGuard(mk(200, 240), 8);      // L* 跨幅約 12 ⇒ 不擋
    assert.strictEqual(wide.ok, true, wide.blocked);
    const mid = E.calibQuadPairGuard(mk(225, 240), 8);       // 跨幅約 4~8，比 K=8 小但 ≥4 ⇒ 仍不擋
    assert(mid.span >= 4 && mid.span < 8, '試資料不在預期區間：' + mid.span);
    assert.strictEqual(mid.ok, true, '跨幅 4~K 之間不該擋（R6-7 附款 C 案）：' + mid.blocked);
    assert.strictEqual(mid.maxLevels, Math.floor(mid.span), '沒把「最多做得出幾階」算出來');
    const narrow = E.calibQuadPairGuard(mk(238, 240), 8);    // 跨幅 <4 ⇒ 擋
    assert.strictEqual(narrow.ok, false);
    assert(/跨幅/.test(narrow.blocked), narrow.blocked);
  });
  await check('🔴 hex 只防呆不當鍵：料色對不上 ⇒ 警示但**不擋**（R6-14 子題 1）', async () => {
    const slots = QSLOTS(); slots[1].color = '#B03A2E';       // 換了一批紅，與表宣告的不同
    slots[0].calib = { table: quadTable(), apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, true, '因為顏色像不像而擋了：' + q.calib.why);
    assert(/換批/.test(q.calib.hexWarn), 'hexWarn 沒講出來：' + q.calib.hexWarn);
  });
  await check("apply:false ⇒ 不套用、候選回理論值（逐位元等於黃金值），但狀態仍回報", async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: false };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, false);
    assert.strictEqual(qdig(q), GOLDEN[8].sha, 'apply:false 還是動到了輸出');
  });
  await check('🔴 R6-7 附款 Q4：回報的跨幅是**48 格候選的全域 L\\* 跨幅**，不是頭尾兩支料的亮度差', async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    const Ls = q.palette.map(p => p.lab[0]);
    const want = Math.max(...Ls) - Math.min(...Ls);
    assert(Math.abs(q.calib.spanL - want) < 1e-9, '跨幅不是候選算出來的：' + q.calib.spanL + ' vs ' + want);
    assert.strictEqual(q.calib.maxLevels, Math.floor(q.calib.spanL));
    /* 陽性對照：頭尾兩支料（白 #F2F0EB、黑 #1A1A1A）的亮度差與全域跨幅**不同**⇒
       若有人改成拿頭尾兩支算（原型 v3 的簡化寫法），這條必轉紅。 */
    const A = q.palette.find(p => p.w[0] === 100), D = q.palette.find(p => p.w[3] === 100);
    assert(A && D, '找不到兩個純色端點');
  });
  await check('全部對都不能用 ⇒ 認帳式地退回理論候選（硬閘門是畫面的事，引擎不擋生成）', async () => {
    const flat = quadTable({ tweak: () => '#808080' });        // 每格都一樣 ⇒ 跨幅 0，六對全擋
    const slots = QSLOTS(); slots[0].calib = { table: flat, apply: true };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, false);
    assert.strictEqual(q.calib.skipped.length, 6);
    assert(/沒有任何一對/.test(q.calib.why), q.calib.why);
    assert.strictEqual(qdig(q), GOLDEN[8].sha, '退回理論時輸出應與未校正相同');
  });


  console.log('\n頁面接線（段 A 接庫＋段 C 四料回程；牌 c-0922-ACC-15）');
  const calHtml2 = fs.readFileSync(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'calibration.html'), 'utf8');
  await check('工作室有載 matlib.js，而且改了 engine.js 有跟著動版本字串（WebView 快取教訓）', () => {
    assert(/<script src="matlib\.js\?v=/.test(idxHtml), '沒載 matlib.js');
    assert(!/engine\.js\?v=20260914b/.test(idxHtml), 'engine.js 改了但版本字串沒動');
    assert(idxHtml.indexOf('matlib.js?v=') < idxHtml.indexOf('engine.js?v='), 'matlib 要在 engine 之前載');
  });
  await check('開機會把舊鍵遷進庫，而且**不刪舊鍵**（段 F 起「清除」鈕隨自動配色退場，沒有任何地方動得了它）', () => {
    assert(/PhotoTileMatLib\.migrateLegacy\(/.test(idxHtml), '開機沒跑遷移');
    assert(/PhotoTileMatLib\.readLegacyRaw\(\)/.test(idxHtml), '沒讀舊鍵');
    /* 車 1／車 2 時唯一能刪它的是校正區的「清除」鈕（＝回到自動配色）；R6-16 之後自動配色退場、那顆鈕跟著拿掉 ⇒ 應為 0。 */
    assert.strictEqual((idxHtml.match(/removeItem\(CALIB_LS_KEY\)/g) || []).length, 0,
      '有地方在刪舊鍵（rollback 的退路會被吃掉）');
  });
  /* 車 1 這條守「四料表不走舊的單一格」（calibAcceptRaw 的四料分流在寫舊鍵之前 return）。段 F（車 3）起雙料也不寫舊鍵了
     （計畫 §四段 A「庫存在之後就不再寫它」；照寫會讓下次開機再遷進來一次、清單多一組以色碼命名的重複項）
     ⇒ **有意識地改成**更強的守衛：整頁沒有任何地方寫舊鍵，收下的表一律只進材料庫。 */
  await check('🔴 收下的表一律只進材料庫、整頁沒有任何地方寫舊鍵（四料不會蓋掉雙料表，雙料也不會在下次開機變成重複項）', () => {
    const i0 = idxHtml.indexOf('function calibAcceptRaw(raw){');
    assert(i0 > 0, '找不到 calibAcceptRaw');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\n}', i0));
    assert(/matlibRecord\(tbl[,)]/.test(body), '收下的表沒寫進材料庫');
    const writesLegacy = src => /setItem\(\s*(CALIB_LS_KEY|'ping_phototile_calib_dual_v1')/.test(src.replace(/\/\*[\s\S]*?\*\//g, ''));
    assert(!writesLegacy(idxHtml), '還有地方在寫舊鍵');
    // 陽性對照：把車 2 那行寫舊鍵放回去，守衛必須抓到
    assert(writesLegacy(idxHtml + "\ntry{ localStorage.setItem(CALIB_LS_KEY, JSON.stringify(tbl.raw)); }catch(e){}"), '守衛抓不到寫舊鍵');
  });
  await check('🔴 遷移看內容：舊鍵那張表認領過（身分換了、id 變了）之後重開，不會再遷進來一次', () => {
    const lb = M.emptyLib();
    const legacy = E.calibParseTable(tableGray);
    assert.strictEqual(M.migrateLegacy(lb, legacy, {}).added, true);
    const p = lb.pairs[0];
    M.claimPair(lb, p.id, { fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '深灰' }, { claimedAt: '2026-09-23' });
    const again = M.migrateLegacy(lb, legacy, {});
    assert.strictEqual(again.added, false, '認領過的舊表又被遷進來一次（清單多一組以色碼命名的重複項）');
    assert.strictEqual(lb.pairs.length, 1);
    // 陽性對照：量測點不同的另一張舊表照樣遷得進來（不是一律擋）
    const other = E.calibParseTable(TABLE_BLUE);
    assert.strictEqual(M.migrateLegacy(lb, other, {}).added, true, '內容不同的舊表被擋掉了');
  });
  await check('🔴 四料開校正覆蓋層要帶四個料色，校正頁也要吃得下（不帶＝表宣告了四個無關的顏色且不報錯）', () => {
    assert(/slotCount===4\)\{[\s\S]{0,400}&a=\$\{hx\[0\]\}&b=\$\{hx\[1\]\}&c=\$\{hx\[2\]\}&d=\$\{hx\[3\]\}/.test(idxHtml),
      '工作室沒帶四個料色給校正頁');
    assert(/q\.get\('layout'\)!=='vstrip' && SLOT_N===4/.test(calHtml2), '校正頁沒吃四料的料色參數');
    assert(/\['a','b','c','d'\]\.forEach/.test(calHtml2), '校正頁沒把四個料色套回 SLOTS');
  });
  /* 🔴 車 1 這條原本守「四料的套用還沒開（要等段 F）」——段 F（車 3，牌 c-0923-ACC-23）就是那個「等」的終點，
     這裡**有意識地改成**守開了之後的形狀：套用只從材料庫選的那組來，而且畫面接上了（不是默默生效）。 */
  await check('🔴 段 F：四料的**套用**開了——只從材料庫選的那組來，畫面有選料處、半狀態的說明已拿掉', () => {
    assert(/function calibRequest\(\)\{ return window\.PhotoTileMatFlow \? PhotoTileMatFlow\.calibRequest\(\) : null; \}/.test(idxHtml),
      'calibRequest 不是問 matflow 選的那組（料→圖 R6-16）');
    assert(!/四料的套用還沒接上畫面/.test(idxHtml), '「四料的套用還沒接上畫面」這句半狀態的說明還在（現在是假話）');
    assert(/id="matPanel"/.test(idxHtml), '沒有第 1 步「選顏色」的位置——那就是默默生效');
    assert(!/calibTable && slotCount===2/.test(idxHtml), '舊的「只給雙料」條件還在');
  });
  /* 🆕 2026-09-23 Eric 裁（牌 c-0923-ACC-25，原話「Q1 Q2 Q3照建議」）：「選顏色」住在右欄「列印設定」卡片最上面、色階數上方。
     起因＝放在頂端橫跨三欄時，展開／收起會把原圖與列印模擬兩張圖整個往下推，而且自成一個新區塊。 */
  await check('🔴 第 1 步「選顏色」在右欄「列印設定」卡片裡、色階數上方——不在頂端跨欄、不在左欄', () => {
    const ctrlAt = idxHtml.indexOf('<section class="panel ctrl">');
    const matAt = idxHtml.indexOf('id="matPanel"'), lvAt = idxHtml.indexOf('id="levelsRow"');
    assert(ctrlAt > 0 && matAt > ctrlAt && lvAt > matAt, '#matPanel 不在「列印設定」卡片裡、或不在色階數上方');
    const nextSection = idxHtml.indexOf('<section', ctrlAt + 1);
    assert(nextSection < 0 || matAt < nextSection, '#matPanel 跑出「列印設定」卡片了');
    assert(!/<section class="panel" id="matPanel">/.test(idxHtml), '還是頂端那張獨立的卡（會推動兩張圖）');
    assert(!/#matPanel\{grid-column:1\/-1;/.test(fs.readFileSync(path.join(WEB, 'matflow.css'), 'utf8')), 'matflow.css 還在讓它橫跨三欄');
  });

  /* ================= 車 2 段 E（牌 c-0923-ACC-21）：四料也「把圖的明暗壓進可印範圍再分階」（R6-16 推論③） =================
     兩端＝候選色（實測內插）的 L* 全域最小／最大；映射用雙料那一支 toneStretch()（不寫第二份）。 */
  console.log('\n段 E｜四料 toneStretch（R6-16 推論③）');
  /* 🔒 黃金值的來源＝**段 E 改動前的 engine.js**（分支 claude/pt-matlib2-0923 在 62d72b668b 時）實跑：
     套了四料校正、沒要 toneMap 的標籤。段 E 之後必須逐位元相同——沒要 stretch 的人，印出來的東西不能變。 */
  const GOLDEN_E = { 4: '747c8d34bf5bdc59bfb95121aa5919b9b55138fc8dac79cde2f1d253ea37868e',
                     8: 'db12b6a68fb466b19b34fd306d030115e6a37dd48aac05b22c85167462ca69d7' };
  await check('🔒 段 E 保命索：套了四料校正但沒要 toneMap ⇒ 標籤與段 E 改動前逐位元相同（K=4／K=8）', async () => {
    for (const K of [4, 8]){
      for (const tm of [undefined, 'none']){
        const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: true, toneMap: tm };
        const q = await E._internals.quantizeQuad(quadImg(), { klevels: K }, slots, null);
        assert.strictEqual(q.calib.applied, true, q.calib.why);
        assert.strictEqual(qdig(q), GOLDEN_E[K], 'K=' + K + ' toneMap=' + tm + ' 標籤變了');
        assert.strictEqual(q.calib.toneMap, undefined, '沒要 stretch 卻記了映射');
      }
    }
  });
  await check("段 E：toneMap:'stretch' ⇒ 啟動映射，兩端＝候選 L* 的最小／最大；標籤必須與沒要時不同（陽性對照）", async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: true, toneMap: 'stretch' };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, true, q.calib.why);
    const tm = q.calib.toneMap;
    assert(tm && tm.mode === 'stretch', '沒記映射：' + JSON.stringify(tm));
    /* 候選 L* 的兩端＝palette 用到的只是子集，這裡用 spanL（同一個口徑算的全域跨幅）對：light−dark 必須等於它 */
    assert(Math.abs((tm.light - tm.dark) - q.calib.spanL) < 1e-9, '映射兩端不是候選 L* 的全域兩端：' + JSON.stringify(tm) + ' spanL=' + q.calib.spanL);
    assert.notStrictEqual(qdig(q), GOLDEN_E[8], 'stretch 開了等於沒開');
  });
  await check("段 E：apply:false＋stretch ⇒ 不映射，標籤＝理論候選那一份（映射只跟著「表已套用」走）", async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: false, toneMap: 'stretch' };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.toneMap, undefined);
    assert.strictEqual(qdig(q), GOLDEN[8].sha, 'apply:false 時應與 calib 缺席同一份標籤');
  });
  await check("段 E：六對全被護欄擋下＋stretch ⇒ 不映射（沒有實測範圍可以壓）", async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable({ tweak: () => '#808080' }), apply: true, toneMap: 'stretch' };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 8 }, slots, null);
    assert.strictEqual(q.calib.applied, false);
    assert.strictEqual(q.calib.toneMap, undefined);
  });
  await check('段 E：這件事真正的用途——圖的明暗很窄（L* 40～60）時，壓進可印範圍之後用到的色階變多（K 階都有肉）', async () => {
    const w = 16, h = 16, n_ = w * h; const lab = new Float32Array(n_ * 3);
    for (let p = 0; p < n_; p++){ lab[p*3] = 40 + 20 * p / (n_ - 1); lab[p*3+1] = 0; lab[p*3+2] = 0; }
    const narrow = () => ({ w, h, lab: lab.slice(), lum: new Float32Array(n_), data: new Uint8ClampedArray(n_ * 4) });
    const distinct = q => new Set(q.rawLabels).size;
    const s0 = QSLOTS(); s0[0].calib = { table: quadTable(), apply: true };
    const s1 = QSLOTS(); s1[0].calib = { table: quadTable(), apply: true, toneMap: 'stretch' };
    const q0 = await E._internals.quantizeQuad(narrow(), { klevels: 8 }, s0, null);
    const q1 = await E._internals.quantizeQuad(narrow(), { klevels: 8 }, s1, null);
    assert(distinct(q1) > distinct(q0), '壓進可印範圍之後用到的階數沒有變多：' + distinct(q0) + ' → ' + distinct(q1));
  });

  /* ================= 車 2 段 D（牌 c-0923-ACC-21）：suggest() 退場＝料 → 圖（R6-16） =================
     頁面邏輯住在 index.html（node 載不進來）⇒ 這裡做**結構守衛**，而且每一條都配陽性對照
     （把被守的東西放回去，守衛必須轉紅——否則不知道它有沒有在看）。執行期的 R6-13 驗收
     （手動設色／匯入校正表之後，無論再載幾張圖槽色都不變）另在瀏覽器實走。 */
  /* 找「程式碼裡」的 suggest( 呼叫：先去掉 /* *\/ 區塊註解與 <!-- --> 註解，行內 // 之後的也不算。 */
  const suggestCallsIn = src => {
    const noBlock = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '');
    const hits = [];
    noBlock.split(/\r?\n/).forEach((ln, i) => {
      const k = ln.search(/(^|[^\w.])suggest\s*\(/);
      if (k < 0) return;
      const cmt = ln.indexOf('//');
      if (cmt >= 0 && cmt < k) return;
      hits.push(ln.trim());
    });
    return hits;
  };
  await check('🔴 R6-16 段 D：頁面程式碼裡不再有 suggest()——函式本體退場、四個呼叫點全拆（含陽性對照）', () => {
    const hits = suggestCallsIn(idxHtml);
    assert.deepStrictEqual(hits, [], '頁面還有 suggest( 呼叫或定義：' + hits.join(' ｜ '));
    assert(!/function suggest\s*\(/.test(idxHtml.replace(/\/\*[\s\S]*?\*\//g, '')), 'function suggest( 還在（註解裡提到不算）');
    // 陽性對照：把「開圖即自動建議」放回去，守衛必須抓到
    const mutated = idxHtml.replace('  renderSlots(); simulate();\n', '  suggest();\n').replace('  renderSlots(); simulate();\r\n', '  suggest();\r\n');
    assert(mutated !== idxHtml, '陽性對照沒改到東西（錨點失效）');
    assert(suggestCallsIn(mutated).length >= 1, '守衛抓不到被放回去的 suggest()');
  });
  await check('🔴 R6-16 段 D：開圖（loadBitmap）不改料色——只照目前的料出模擬', () => {
    const i0 = idxHtml.indexOf('function loadBitmap(bmp, label){');
    assert(i0 > 0, '找不到 loadBitmap');
    const i1 = idxHtml.indexOf('\nfunction ', i0 + 10);
    const body = idxHtml.slice(i0, i1 > 0 ? i1 : i0 + 4000).replace(/\/\*[\s\S]*?\*\//g, '');
    assert(/renderSlots\(\); simulate\(\);/.test(body), '開圖之後沒有出模擬（零點擊先看到結果被拿掉了）');
    assert(!/slots\[[^\]]*\](\.color)?\s*=[^=]/.test(body), '開圖時還在改料槽');
  });
  await check('🔴 R6-16 段 D：AI 回圖不再依圖改料色（R9-10 在選色這一關被取代）', () => {
    const i0 = idxHtml.indexOf('async aiEnd(m){');
    assert(i0 > 0, '找不到 aiEnd');
    const body = idxHtml.slice(i0, idxHtml.indexOf('ptSourceTitle(\'ai\');', i0)).replace(/\/\*[\s\S]*?\*\//g, '');
    assert(!/slots\[[^\]]*\](\.color)?\s*=[^=]/.test(body), 'AI 回圖時還在改料槽');
    assert(/simulate\(\);/.test(body), 'AI 回圖之後沒有照目前的料出模擬');
  });
  await check('🔴 R6-16 段 D：「依這張圖建議配色」語意反轉成「依料重算圖面顏色」，按它不改料色、不收回「已套用」', () => {
    assert(/id="btnSuggest"[^>]*>[\s\S]{0,80}重算圖面顏色<\/button>/.test(idxHtml), '按鈕字沒換成「依料重算圖面顏色」');
    assert(!/建議配色<\/button>/.test(idxHtml), '舊的「建議配色」按鈕字還在');
    assert(/getElementById\('btnSuggest'\)\.onclick=recolorFromMaterials;/.test(idxHtml), '按鈕沒接到 recolorFromMaterials');
    const i0 = idxHtml.indexOf('function recolorFromMaterials(){');
    assert(i0 > 0, '找不到 recolorFromMaterials');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\n}', i0)).replace(/\/\*[\s\S]*?\*\//g, '');
    assert(!/slots\[[^\]]*\](\.color)?\s*=[^=]/.test(body), '「依料重算」在改料槽——方向又反了');
    assert(/ptSourceKind==='style' && ptLastStyleJob/.test(body), '壓平過的圖沒有照新的料重壓（舊色階會騎在新門檻上）');
    assert(!/sgEl\.addEventListener\('click'/.test(idxHtml), '按「依料重算」仍會收回「已套用」（它已不改料色，不算偏離款式）');
  });
  await check('R6-16 段 D：引擎的 suggestSlots() 仍在——C++ 黃金閘門 12 個基準案全靠它（請求不帶料色時）', () => {
    const E = require(path.join(__dirname, '..', '..', 'resources', 'web', 'phototile', 'engine.js'));
    assert.strictEqual(typeof E.suggestSlots, 'function', 'engine.suggestSlots 不見了（黃金閘門會全紅）');
  });

  /* ================= 車 3 段 F（牌 c-0923-ACC-23）：產圖流程第 1 步「選顏色」＋校正流程（matflow.js） =================
     純邏輯直接 require（matflow.js 與 matlib.js 同形，node 載得進來）；頁面接線做結構守衛，能配陽性對照的都配。
     料用真表：0914 白×深灰（tableGray）、0822 白×藍／白×黃（檔頭那兩張），四料用 48 格合成表（quadTable）。 */
  console.log('\n段 F｜選顏色（料→圖 R6-16）＋校正流程（matflow.js）');
  const F = require(path.join(WEB, 'matflow.js'));
  const MF_SRC = fs.readFileSync(path.join(WEB, 'matflow.js'), 'utf8');
  const libF = () => {
    const lb = M.emptyLib();
    const put = (raw, a, b, at) => M.upsertPair(lb, M.pairFromDual(E.calibParseTable(raw), { materials: [a, b], measuredAt: at }));
    put(tableGray,    { fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '深灰' }, '2026-09-14');
    put(TABLE_BLUE,   { fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '淺藍' }, '2026-08-22');
    put(TABLE_YELLOW, { fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '黃' },   '2026-08-22');
    return lb;
  };
  const keyOf = (lb, label) => M.listMaterials(lb).find(m => m.label === label).key;
  await check('🔴 R6-16 推論①：清單只有量過的料；選第二支起照「這一對有沒有一起校正過」判，選不到的不藏、原因寫在列上', () => {
    const lb = libF();
    assert.deepStrictEqual(F.choices(lb, 'dual', []).rows.map(r => r.state), ['ok', 'ok', 'ok', 'ok']);
    const ch = F.choices(lb, 'dual', [keyOf(lb, '深灰')]);
    const st = l => ch.rows.find(r => r.mat.label === l);
    assert.strictEqual(st('白').state, 'ok');
    assert.strictEqual(st('淺藍').state, 'no', '淺藍沒和深灰一起量過卻選得到（那一對的混色沒人量過）');
    assert(/沒和「深灰」一起校正過/.test(st('淺藍').why), st('淺藍').why);
    assert.strictEqual(ch.rows.length, M.listMaterials(lb).length, '有料被藏起來了（選不到要講為什麼，不是消失：FBK-11）');
  });
  await check('🔴 擠出機 1 放最淺的；料色＝**這一對**量到的兩端（同一支料在別對量到的色不同，拿錯＝引擎整段不套用）', () => {
    const lb = M.emptyLib();
    M.upsertPair(lb, M.pairFromDual(E.calibParseTable(tableGray), { materials: [{ fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '深灰' }] }));
    const pts = TABLE_BLUE['量測'].map(r => [r['配方'].S, r['量到色']]); pts[0][1] = '#EFEEEA';
    M.upsertPair(lb, M.pairFromDual(E.calibParseTable(mkTable('#EFEEEA', '#93D9FA', pts)), { materials: [{ fid: 'GPLA', label: '白' }, { fid: 'GPLA', label: '淺藍' }] }));
    const inf = F.setInfo(lb, 'dual', [keyOf(lb, '淺藍'), keyOf(lb, '白')]);
    assert.deepStrictEqual(inf.mats.map(m => m.label), ['白', '淺藍'], '擠出機 1 不是最淺的');
    assert.deepStrictEqual(inf.colors, ['#EFEEEA', '#93D9FA'], '料色不是這一對量到的兩端');
    const req = F.calibRequestFor(lb, inf, { calibGen: true, calibStretch: true });
    assert.strictEqual(req.toneMap, 'stretch');
    const lad = E.dualLadderCalibrated(inf.colors.map(c => ({ color: c })), 8, req);
    assert.strictEqual(lad.calib.applied, true, lad.calib.why);
    // 陽性對照：拿清單上那支白的色（量自別對）⇒ 料色對不上、整段不套用
    const other = M.listMaterials(lb).find(m => m.label === '白').hex;
    assert.notStrictEqual(other, '#EFEEEA', '陽性對照前提不成立');
    assert.strictEqual(E.dualLadderCalibrated([{ color: other }, { color: '#93D9FA' }], 8, req).calib.applied, false, '陽性對照沒轉紅');
  });
  await check('🔴 toDualCalibTable：槽位順序與量測當下相反 ⇒ S 翻回、料色對調，引擎照樣套得上（不翻＝整條曲線頭尾顛倒）', () => {
    const lb = libF(), mats = M.listMaterials(lb);
    const w = mats.find(m => m.label === '白'), g = mats.find(m => m.label === '深灰');
    const t = M.toDualCalibTable(lb, g, w).table;
    assert.strictEqual(t['料'][0]['色'], '#707279');
    assert.deepStrictEqual(t['量測'].map(r => r['配方'].S), E.calibParseTable(tableGray).pts.map(p => Math.round((1 - p.S) * 100) / 100));
    const lad = E.dualLadderCalibrated([{ color: t['料'][0]['色'] }, { color: t['料'][1]['色'] }], 8, { table: t, apply: true });
    assert.strictEqual(lad.calib.applied, true, lad.calib.why);
    assert.strictEqual(M.toDualCalibTable(lb, g, mats.find(m => m.label === '淺藍')).table, null, '沒量過的一對吐出了一張表');
  });
  await check('🔴 R6-7 附款：上限＝floor(實測跨幅)（白×黃 4.6 ⇒ 最多 4 階）；跨幅 < 4 的那一對選不到、講得出為什麼', () => {
    const inf = F.setInfo(libF(), 'dual', [keyOf(libF(), '白'), keyOf(libF(), '黃')]);
    assert.strictEqual(inf.cap, 4, 'cap=' + (inf && inf.cap));
    const lb2 = M.emptyLib();
    const hx = ['#F2F0EB', '#F1EFEA', '#F0EEE9', '#EFEDE8', '#EEECE7', '#EDEBE6', '#ECEAE5', '#EAE8E3'];
    const SS = [1, 0.86, 0.71, 0.57, 0.43, 0.29, 0.14, 0];
    M.upsertPair(lb2, M.pairFromDual(E.calibParseTable(mkTable('#F2F0EB', '#EAE8E3', hx.map((h, i) => [SS[i], h]))),
      { materials: [{ fid: 'X', label: '白' }, { fid: 'X', label: '米白' }] }));
    const ch = F.choices(lb2, 'dual', []);
    assert(ch.rows.every(r => r.state === 'no'), '跨幅 < 4 的那一對還選得到');
    assert(/都不能用/.test(ch.rows[0].why), ch.rows[0].why);
    assert(/連 4 階都做不出來/.test(F.setCheck(lb2, 'dual', M.listMaterials(lb2).map(m => m.key)).why));
  });
  await check('🔴 四料：六對都要一起量過；被護欄擋下的那一對只排除它的混色（R6-4）、不擋整組；上限看候選全域跨幅（R6-7 附款 Q4）', () => {
    const ids = QNAME.map(n => ({ fid: 'Q', label: n }));
    const build = tbl => { const lb = M.emptyLib(); M.pairsFromQuad(E.calibParseTable(tbl), { materials: ids, measuredAt: '2026-09-23' }).forEach(p => M.upsertPair(lb, p)); return lb; };
    // 紅×藍亮度只差 2.6（逐對護欄擋下），整組仍選得起來，那一對列進「不會用到」
    const lb = build(quadTable({ colors: ['#F2F0EB', '#C0392B', '#2E6BD8', '#1A1A1A'] }));
    const ks = QNAME.map(n => keyOf(lb, n));
    const inf = F.setInfo(lb, 'quad', [ks[3], ks[1], ks[2], ks[0]]);
    assert(inf, '有一對被護欄擋下就整組選不起來（四料幾乎組不起來）');
    assert.strictEqual(inf.mats[0].label, '白', '擠出機 1 不是最淺的');
    /* 🔴 其餘照給進來的順序（校正帶過來的＝校正當下的擠出機順序）：全部照亮到暗重排會把藍（L* 47）搬到紅（43）前面，
       人照校正時裝好的料去印就錯色。 */
    assert.deepStrictEqual(F.setInfo(lb, 'quad', [ks[1], ks[2], ks[0], ks[3]]).mats.map(m => m.label), ['白', '紅', '藍', '黑'],
      '除了最淺那支放擠出機 1，其餘沒照給的順序');
    assert(inf.pairs.some(v => !v.ok) && /紅×藍[^；]*不會用到|藍×紅[^；]*不會用到/.test(inf.warn), '被擋的那一對沒講出來：' + inf.warn);
    const req = F.calibRequestFor(lb, inf, { calibGen: true, calibStretch: false });
    const qc = E.quadCandidates(inf.colors.map(c => ({ color: c })), 8, req);
    assert.strictEqual(qc.plan.applied, true);
    assert.strictEqual(inf.cap, Math.min(8, Math.floor(qc.Lmax - qc.Lmin)), '上限不是候選的全域跨幅');
    // 少一對沒量（R6＝藍×黑）⇒ 選了白紅藍之後「黑」選不到、理由點名藍
    const lbMiss = build(quadTable({ dropRow: 6 }));
    const ch = F.choices(lbMiss, 'quad', ['白', '紅', '藍'].map(n => keyOf(lbMiss, n)));
    const k = ch.rows.find(r => r.mat.label === '黑');
    assert.strictEqual(k.state, 'no'); assert(/沒和「藍」一起校正過/.test(k.why), k.why);
  });
  await check('選滿之後再點另一支＝從那支重新開始（原型的「擠掉最早那支」在 pair 庫上會假標「選不到」）', () => {
    assert.deepStrictEqual(F.toggle(['a', 'b'], 'c', 2), ['c']);
    assert.deepStrictEqual(F.toggle(['a', 'b'], 'a', 2), ['b']);
    assert.deepStrictEqual(F.toggle(['a'], 'b', 2), ['a', 'b']);
    const lb = libF();
    const ch = F.choices(lb, 'dual', [keyOf(lb, '白'), keyOf(lb, '深灰')]);
    assert(ch.rows.filter(r => r.state !== 'picked').every(r => r.state === 'ok'), '選滿時其他料被假標成選不到');
  });
  await check('預設那一組：上次選的還在就用它，否則用最近量的那組；🔴 空庫不得發明一組（R6-16）', () => {
    const lb = libF();
    const last = [keyOf(lb, '白'), keyOf(lb, '淺藍')];
    assert.deepStrictEqual(F.defaultKeys(lb, 'dual', last), last);
    const d = F.defaultKeys(lb, 'dual', ['不存在的那支']);
    assert.deepStrictEqual(d.map(k => M.listMaterials(lb).find(m => m.key === k).label).sort(), ['深灰', '白'].sort(), '不是最近量的那組');
    assert.deepStrictEqual(F.defaultKeys(M.emptyLib(), 'dual', []), []);
  });
  await check('🔴 Q1（R6-15）：AI 提示詞那一行帶的是這組料量到的顏色、接在 toneRules 後面；沒選料不產圖', () => {
    const lb = libF();
    const line = F.aiPaletteLine(F.setInfo(lb, 'dual', [keyOf(lb, '白'), keyOf(lb, '深灰')]));
    assert(line.includes('#F2F0EB') && line.includes('#707279') && /mix of any two/.test(line), line);
    assert.strictEqual(F.aiPaletteLine(null), '');
    const i0 = idxHtml.indexOf('function ptAiGenerate(s, tones){');
    assert(i0 > 0, '找不到 ptAiGenerate');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\n}', i0));
    const iTone = body.indexOf('STYLE_LIB.constants.toneRules'), iPal = body.indexOf('PhotoTileMatFlow.aiPaletteLine(');
    assert(iTone > 0 && iPal > iTone, '色盤那一行沒接在 toneRules 後面（放上面會被它讓位）');
    assert(/if\(!calibOwnsSlots\(\)\)\{/.test(body), '沒選料也照樣產圖（R6-15：先有顏色）');
  });
  await check('🔴 認領（R6-14 子題 2 附款）：沒有 filament_id 的那組選到時要認領；認領後出身保留；跳過要記住（一次性）', () => {
    const lb = M.emptyLib();
    M.migrateLegacy(lb, E.calibParseTable(tableGray), {});
    const inf = F.setInfo(lb, 'dual', M.listMaterials(lb).map(m => m.key));
    assert.strictEqual(inf.claim.length, 1, '舊表那組沒被標成要認領');
    const map = new Map([[inf.mats[0].key, { fid: 'GPLA', label: '白' }], [inf.mats[1].key, { fid: 'GPLA', label: '深灰' }]]);
    const ren = F.claimMaterials(lb, map, '2026-09-23');
    assert.strictEqual(lb.pairs.length, 1);
    assert.strictEqual(lb.pairs[0].source, 'legacy-hex', '認領把出身洗掉了（要可追溯）');
    const after = F.setInfo(lb, 'dual', inf.keys.map(k => ren.get(k)));
    assert(after && after.claim.length === 0, '認領之後還要再問');
    const lb2 = M.emptyLib(); M.migrateLegacy(lb2, E.calibParseTable(tableGray), {});
    lb2.pairs[0].claimSkippedAt = '2026-09-23';
    const again = M.parseLib(JSON.stringify(lb2)).lib;          // 存回檔、再讀回來
    assert.strictEqual(F.setInfo(again, 'dual', M.listMaterials(again).map(m => m.key)).claim.length, 0, '跳過存回檔就忘了＝不是一次性');
  });
  await check('R8-5 實跑：quantizeQuad 用到的每一個零件色都在 quadCandidates 的候選裡、跨幅同一個數（預覽與生成同一把尺）', async () => {
    const slots = QSLOTS(); slots[0].calib = { table: quadTable(), apply: true, toneMap: 'stretch' };
    const q = await E._internals.quantizeQuad(quadImg(), { klevels: 6 }, slots, null);
    const qc = E.quadCandidates(QSLOTS(), 6, slots[0].calib);
    const keys = new Set(qc.cands.map(c => c.w.join(',')));
    q.palette.forEach(p => assert(keys.has(p.w.join(',')), '零件色 ' + p.w + ' 不在候選裡'));
    assert.strictEqual(q.calib.spanL, qc.Lmax - qc.Lmin);
  });
  await check('🔴 R8-5 兩把尺（結構）：四料預覽的候選色問引擎 quadCandidates、映射問 quadToneStretch，頁面不再自己算 mixLin', () => {
    const i0 = idxHtml.indexOf('function simulateVerticalQuad(){');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\nfunction ', i0 + 10)).replace(/\/\*[\s\S]*?\*\//g, '');
    assert(/eng\.quadCandidates\(slots, K, calibReq\)/.test(body), '預覽的候選色不是引擎那一份');
    assert(/eng\.quadToneStretch\(/.test(body), '預覽沒吃段 E 的映射');
    assert(!/mixLin/.test(body), '預覽還有自己的一份理論候選（mixLin）');
    assert(/const qc = quadCandidates\(slots, K, calib\);/.test(fs.readFileSync(path.join(WEB, 'engine.js'), 'utf8')), 'quantizeQuad 沒走 quadCandidates');
  });
  await check('🔴 R6-16：料槽不再是取色器（任意改色＝可以設一個沒量過的顏色）；小色塊點了打開第 1 步', () => {
    const i0 = idxHtml.indexOf('function renderSlots(){');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\n}', i0));
    assert(!/type="color"/.test(body), 'renderSlots 還在畫取色器');
    assert(/PhotoTileMatFlow\.chipsHtml\(slotCount\)/.test(body), '料槽不是材料庫那組的小色塊');
    assert(/data-mf="open"/.test(MF_SRC) && /openPicker\(\)/.test(MF_SRC), '小色塊點了打不開第 1 步');
  });
  await check('🔴 R6-15 附款＋LAY-21：色彩校正不再常駐右欄、搬進「校正流程」五步；兩個開關降級到「進階」', () => {
    assert(!/id="calibDetails"/.test(idxHtml), '右欄還有色彩校正段');
    const s0 = idxHtml.indexOf('<section id="calFlow"');
    assert(s0 > 0, '沒有校正流程');
    const cf = idxHtml.slice(s0, idxHtml.indexOf('</section>', s0));
    assert.strictEqual((cf.match(/class="calStep" data-step="/g) || []).length, 5, '校正流程不是五步');
    ['btnCalib', 'btnCalibOverlay', 'calibFile'].forEach(id => assert(cf.includes('id="' + id + '"'), id + ' 不在校正流程裡'));
    const a0 = idxHtml.indexOf('<details id="advDetails">');
    const adv = idxHtml.slice(a0, idxHtml.indexOf('</details>', a0));
    assert(adv.includes('id="calibGenChk"') && adv.includes('id="calibStretchChk"'), '兩個開關沒降級到「進階」');
    assert(/id="flowSeg"/.test(idxHtml), '沒有兩條流程的切換');
  });
  await check('🔴 FBK-11：還沒選顏色 ⇒「產生」講缺什麼並給一顆去選的鈕；模擬不拿理論色頂上', () => {
    const i0 = idxHtml.indexOf("document.getElementById('btnExport').onclick=async()=>{");
    const body = idxHtml.slice(i0, i0 + 700);
    assert(/if\(!calibOwnsSlots\(\)\)\{ genStatline\('warn'/.test(body), '產生沒擋沒選料的情形');
    assert(/openPicker\(\)/.test(body), '擋下時沒給出口');
    assert(/function simulate\(\)\{[\s\S]{0,200}if\(!calibOwnsSlots\(\)\)\{ simulateBlank\(\); return; \}/.test(idxHtml), '沒選料時模擬拿理論色頂上');
  });
  await check('LAY-15：套款式的確認框「確定」在左、「取消」恆在最右；預設焦點仍在取消', () => {
    const i0 = idxHtml.indexOf('function ptConfirmApply(');
    const body = idxHtml.slice(i0, idxHtml.indexOf('\nfunction ', i0 + 10));
    assert(/btns\.appendChild\(yes\); btns\.appendChild\(no\);/.test(body), '鈕序不是肯定在左、取消在右');
    assert(/no\.focus\(\)/.test(body), '預設焦點不在取消');
    assert(/data-c="yes">指定<\/button>'\s*\+ '<button type="button" class="btn" data-c="no">/.test(MF_SRC), '認領窗的鈕序不是肯定在左');
  });
  await check('matflow.js／matflow.css 有掛上而且帶版本字串；matflow 在 engine 之後載；🔴 index.html 不再往讀取上限長', () => {
    assert(/<script src="matflow\.js\?v=/.test(idxHtml) && /href="matflow\.css\?v=/.test(idxHtml), '沒掛或沒帶版本字串（WebView 快取教訓）');
    assert(idxHtml.indexOf('engine.js?v=') < idxHtml.indexOf('matflow.js?v='), 'matflow 要在 engine 之後載');
    const bytes = Buffer.byteLength(idxHtml, 'utf8');
    assert(bytes < 0.92 * 262144, 'index.html ' + bytes + ' B 超過讀取上限的 92%——新碼請放獨立檔（Read 到上限會讀一半就停、不報錯）');
  });

  console.log(`\n${pass} 通過、${fail} 失敗`);
  process.exit(fail ? 1 : 0);
})();
