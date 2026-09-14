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
    for (const k of ['calibParseTable','calibLookupLin','calibMatches','calibGenLadder','dualLadderCalibrated','buildCalibStrip','buildCalibStripParts','calibStripDefaultS'])
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
  check('buildCalibStripParts：8 零件、名稱尾端 S1／S0.94／…／S0、Z 由下往上 6 mm 一階', () => {
    const c = E.buildCalibStripParts({ hexA: '#F2F0EB', hexB: '#5D6268', nameA: '白', nameB: '深灰', widthMm: 80, thickMm: 8, bandMm: 6 });
    const names = [...c.cfg.matchAll(/key="name" value="([^"]+)"/g)].map(m => m[1]);
    assert.strictEqual(names.length, 9);   // 1 物件名＋8 零件
    assert.deepStrictEqual(names.slice(1).map(n => n.split(' ').pop()), ['S1','S0.94','S0.87','S0.78','S0.67','S0.53','S0.35','S0']);
    assert.strictEqual(c.height, 48);
    assert((c.model.match(/paint_seam="8"/g) || []).length, 8 * 4);   // 每階正／背面各 2 三角形
    assert(!/paint_seam="4"/.test(c.model), '直立條不標接著面');
    assert(c.model.includes('PING-PhotoTile-ColorCalib'));
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

  console.log(`\n${pass} 通過、${fail} 失敗`);
  process.exit(fail ? 1 : 0);
})();
