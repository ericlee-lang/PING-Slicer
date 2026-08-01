/* =====================================================================
   PhotoTileEngine — 照片磚 C 案引擎（C-1 產品版，2026-07-31；照片磚線 PT）
   generate(request) → Promise<result>：把工作室頁（index.html）的生成鏈抽成
   「脫離 DOM 狀態」的引擎 API。所有數學／演算法逐行搬自 index.html（行號註記
   ＝搬運出處；為黃金比對，語意必須逐位元一致），只做三類改寫：
     ① params/slots/img/lastExport 全域 → request 欄位與區域變數
     ② DOM 回寫（statline/metric/canvas 畫面）→ result.diagnostics
     ③ 錯誤 → 具代碼的 EngineError（result.error）
   依賴：PhotoTileMesh（mesh_union.js，本就是 UMD 純函式模組）。
   執行環境需求：OffscreenCanvas、createImageBitmap、CompressionStream、performance
   —— 皆為 Worker 可用 API；頁面／Worker／WebView2 隱形宿主皆可跑。

   ⚠ 零計時器紀律（C-0 §3.2 紅字發現）：隱形頁面的 setTimeout 被節流到 ~1s/次。
   本檔生成路徑**不得**出現 setTimeout／setInterval／requestAnimationFrame；
   階段讓步一律走 MessageChannel macrotask（實測免疫節流）。

   C-1 相對 C-0 spike 的四項增補（演算法零變更＝黃金比對仍須 6/6 全等）：
     ① progress 回報（階段權重＋量化熱迴圈分塊回報；合法上限 quad K48 ≈1 分鐘）
     ② limits 可降階（gridMax／maxDecodedPixels＝OOM gate 與低規機保護）
     ③ metadata／原圖嵌入＝**opt-in**（request.metadata 缺席時 3MF 位元組與工作室全等，
        黃金 oracle 因此得以持續有效——這是刻意的設計約束，勿改成預設開）
     ④ env 環境快照原封回傳（C++ 端比對過期即棄）
   ===================================================================== */
(function (root, factory) {
  const api = factory(root);
  root.PhotoTileEngine = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
"use strict";

/* ================= 色彩數學（index.html:207-223 verbatim） ================= */
const GAM = 2.2;
const s2l = c => Math.pow(c/255, GAM);
const l2s = c => Math.round(255*Math.pow(Math.max(0,Math.min(1,c)), 1/GAM));
function hexRgb(h){ h=h.replace('#',''); return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)]; }
function hexLin(h){ return hexRgb(h).map(s2l); }
function rgbHex(r,g,b){ return '#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join(''); }
function lin2lab(r,g,b){
  let x = r*0.4124 + g*0.3576 + b*0.1805;
  let y = r*0.2126 + g*0.7152 + b*0.0722;
  let z = r*0.0193 + g*0.1192 + b*0.9505;
  x/=0.95047; z/=1.08883;
  const f = t => t>0.008856 ? Math.cbrt(t) : (7.787*t + 16/116);
  const fx=f(x), fy=f(y), fz=f(z);
  return [116*fy-16, 500*(fx-fy), 200*(fy-fz)];
}
const lum709 = (r,g,b) => 0.2126*r + 0.7152*g + 0.0722*b;

/* ================= 版本（進 3MF metadata、ready 握手與 goldens 追溯） ================= */
const ENGINE_VERSION = 'C1-20260731';

/* ================= 常數（index.html:234-241, 619-620） ================= */
const AUTO_CELL_MM = 0.05;   // 內部自動高精度格點
const GRID_MAX     = 3200;   // 長邊格數上限
const SIZE_MIN_MM  = 20, SIZE_MAX_MM = 400;
const NOZZLES      = [0.4, 0.6, 1.0];

/* ================= 錯誤分類 ================= */
const ERR = {
  BAD_REQUEST:        'bad_request',          // 參數不合法（訊息含欄位）
  BAD_IMAGE:          'bad_image',            // 影像解碼失敗
  IMAGE_TOO_LARGE:    'image_too_large',      // 解碼後像素數超過 limits.maxDecodedPixels（C-1 OOM gate）
  MESH_MODULE_MISSING:'mesh_module_missing',  // mesh_union.js 未載入
  CANCELLED:          'cancelled',            // 呼叫端取消
  INTERNAL:           'internal'              // 其餘（附原始訊息）
};
class EngineError extends Error {
  constructor(code, message){ super(message); this.code = code; this.name = 'EngineError'; }
}

/* ================= 請求正規化 =================
   夾值範圍照工作室 UI 的 min/max（index.html:140-186 的 input 屬性與 onchange 夾值），
   超界＝夾住並記進 diagnostics.clamped（不是報錯——與工作室輸入框行為一致）。 */
function normalizeRequest(req){
  if (!req || typeof req !== 'object') throw new EngineError(ERR.BAD_REQUEST, 'request 必須是物件');
  const clamped = [];
  const clamp = (name, v, lo, hi, dflt) => {
    let x = Number(v);
    if (!Number.isFinite(x)) x = dflt;
    const y = Math.max(lo, Math.min(hi, x));
    if (y !== Number(v)) clamped.push(`${name}:${v}→${y}`);
    return y;
  };
  const mode = req.mode === 'quad' ? 'quad' : req.mode === 'dual' ? 'dual' : null;
  if (!mode) throw new EngineError(ERR.BAD_REQUEST, `mode 必須是 dual|quad（收到 ${req.mode}）`);
  let nozzle = Number(req.nozzle);
  if (!NOZZLES.includes(nozzle)) throw new EngineError(ERR.BAD_REQUEST, `nozzle 必須是 0.4|0.6|1.0（收到 ${req.nozzle}）`);
  const size = req.size || {};
  const P = {
    jobId:   String(req.jobId || ('job-' + (++jobSeq))),
    mode, nozzle,
    width:  clamp('width',  size.widthMm,  SIZE_MIN_MM, SIZE_MAX_MM, 100),
    height: clamp('height', size.heightMm, SIZE_MIN_MM, SIZE_MAX_MM, 75),
    thick:  clamp('thick',  size.thickMm,  2, 30, 6),                       // index.html:1014-1016
    klevels: Math.round(clamp('klevels', req.klevels, 2, 48, 8)),           // index.html:995-998
    noiseMm: clamp('noiseMm', req.noiseMm, 0, 20, 2.0),                     // index.html:1017-1025
    pillar:  req.pillar ? !!req.pillar.enabled : true,
    pillarXY: Math.round(clamp('pillarXY', req.pillar && req.pillar.xyMm, 5, 60, 25)), // index.html:1029-1031
    teeth:   !!(req.seam && req.seam.teeth),
    p2aBlock:!!(req.seam && req.seam.p2aBlock),
    slots:   Array.isArray(req.slots) && req.slots.length ? req.slots.map(s=>({...s})) : null, // null＝自動建議
    image:   req.image,
    /* C-1：低規機保護。gridMax 預設＝工作室現值 3200（不填＝與工作室全等）；
       maxDecodedPixels 預設 0＝不設限（C-0 §4.3 列的硬化項，由宿主依可用記憶體帶入）。 */
    limits: {
      gridMax: Math.round(clamp('limits.gridMax', (req.limits && req.limits.gridMax) || GRID_MAX, 256, GRID_MAX, GRID_MAX)),
      maxDecodedPixels: Math.max(0, Number((req.limits && req.limits.maxDecodedPixels) || 0) || 0)
    },
    /* C-1：metadata＝opt-in（缺席＝3MF 與工作室位元組全等，黃金 oracle 續用） */
    metadata: (req.metadata && typeof req.metadata === 'object') ? req.metadata : null,
    /* C-1：環境快照原封回傳，引擎不解讀（C++ 端比對 printer/plate/project revision） */
    env: (req.env && typeof req.env === 'object') ? req.env : null,
    clamped
  };
  const need = mode === 'quad' ? 4 : 2;
  if (P.slots && P.slots.length < need)
    throw new EngineError(ERR.BAD_REQUEST, `${mode} 模式 slots 需 ${need} 支（收到 ${P.slots.length}）`);
  return P;
}

/* ================= 影像來源 → ImageBitmap =================
   三形態：ImageBitmap（呼叫端已解碼）／{mime,base64}（原生橋接形態，對應
   index.html:698-704 finishImage 的 data URL 解碼路）／{width,height,rgba}（測試注入）。 */
async function resolveImage(image, limits){
  let bmp = null, source = null, owned = false;       // owned＝引擎自己解碼的，用完要關
  try {
    if (typeof ImageBitmap !== 'undefined' && image instanceof ImageBitmap) {
      bmp = image;                                    // 工作室路徑：呼叫端已解碼、無原始位元組
    } else if (image && typeof image.base64 === 'string') {
      const mime = image.mime || 'image/png';
      const response = await fetch(`data:${mime};base64,${image.base64}`);
      const blob = await response.blob();
      bmp = await createImageBitmap(blob);
      owned = true;
      source = { mime, base64: image.base64, byteLength: blob.size, name: image.name || null };
    } else if (image && image.rgba && image.width > 0 && image.height > 0) {
      const data = new ImageData(new Uint8ClampedArray(image.rgba), image.width, image.height);
      bmp = await createImageBitmap(data);
      owned = true;
    }
  } catch (e) {
    throw new EngineError(ERR.BAD_IMAGE, '影像解碼失敗：' + (e && e.message || e));
  }
  if (!bmp)
    throw new EngineError(ERR.BAD_IMAGE, 'image 需為 ImageBitmap / {mime,base64} / {width,height,rgba}');
  /* C-1 OOM gate：解碼後像素數上限（C-0 §4.3——現行 C++ 只有 64MB 檔案上限、
     解碼後像素無上限；48M px 源圖 decoded bitmap 才是真記憶體壓力）。 */
  const cap = limits && limits.maxDecodedPixels;
  if (cap > 0 && bmp.width * bmp.height > cap) {
    const got = bmp.width * bmp.height;
    if (typeof bmp.close === 'function') bmp.close();
    throw new EngineError(ERR.IMAGE_TOO_LARGE,
      `影像 ${bmp.width}×${bmp.height}＝${(got/1e6).toFixed(1)}M 像素，超過上限 ${(cap/1e6).toFixed(1)}M 像素`);
  }
  return { bitmap: bmp, source, owned };
}

/* ================= 影像 → 格點（index.html:648-674，canvas 畫面與 DOM 文案拿掉） ================= */
function gridDims(widthMm, heightMm, gridMax){
  const cap = gridMax > 0 ? gridMax : GRID_MAX;      // C-1：可降階（預設＝工作室現值 3200）
  let gw = Math.max(2, Math.round(widthMm / AUTO_CELL_MM));
  let gh = Math.max(2, Math.round(heightMm / AUTO_CELL_MM));
  const long = Math.max(gw, gh);
  if (long > cap) { const s = cap/long; gw = Math.max(2, Math.round(gw*s)); gh = Math.max(2, Math.round(gh*s)); }
  return { gw, gh };
}
function buildGridData(bmp, widthMm, heightMm, gridMax){
  const { gw, gh } = gridDims(widthMm, heightMm, gridMax);
  const off = new OffscreenCanvas(gw, gh), c = off.getContext('2d');
  c.drawImage(bmp, 0, 0, gw, gh);
  const d = c.getImageData(0, 0, gw, gh);
  const n = gw*gh, lab = new Float32Array(n*3), lum = new Float32Array(n);
  for (let p=0; p<n; p++){
    const r=s2l(d.data[p*4]), g=s2l(d.data[p*4+1]), b=s2l(d.data[p*4+2]);
    const L=lin2lab(r,g,b);
    lab[p*3]=L[0]; lab[p*3+1]=L[1]; lab[p*3+2]=L[2];
    lum[p]=Math.min(1,Math.pow(lum709(r,g,b),1/GAM));
  }
  const step=Math.max(1,Math.round(Math.sqrt(n/1500))), tl=[];
  for(let y=0;y<gh;y+=step) for(let x=0;x<gw;x+=step){ const p=y*gw+x; tl.push(lab[p*3],lab[p*3+1],lab[p*3+2]); }
  return { w:gw, h:gh, data:d.data, lab, lum, thumbLab:tl };
}

/* ================= 濾除（index.html:347-368，DOM 統計改回傳） ================= */
function filterLabels(labels, img, P, paletteSize, strategy){
  if (!root.PhotoTileMesh) throw new EngineError(ERR.MESH_MODULE_MISSING, '連通網格模組未載入');
  const sx=P.width/img.w, sz=P.height/img.h;
  const smooth=root.PhotoTileMesh.smoothLabelNoise(labels,img.w,img.h,paletteSize,sx,sz,P.noiseMm,strategy);
  const minWidthMm=2*P.nozzle;
  const wide=root.PhotoTileMesh.enforceMinHorizontalWidth(smooth.labels,img.w,img.h,
    Math.max(1,Math.round(minWidthMm/sx)));
  const result=root.PhotoTileMesh.filterSmallComponents(wide.labels,img.w,img.h,sx,sz,P.noiseMm,
    {maxPasses:Math.max(8,Math.min(24,paletteSize+2))});
  let changedPixels=0;
  for(let i=0;i<labels.length;i++) if(result.labels[i]!==labels[i]) changedPixels++;
  const stats={removedComponents:result.removedComponents, changedPixels,
    smoothedPixels:smooth.changedPixels, changedAreaMm2:changedPixels*sx*sz,
    widthChangedPixels:wide.changedPixels, widthMergedRuns:wide.mergedRuns, minWidthMm,
    passes:result.passes, thresholdMm:result.thresholdMm, strategy:smooth.strategy};
  return { labels: result.labels, stats };
}

/* ================= 雙料量化（index.html:474-521 計算部；畫布/metric 拿掉） =================
   C-1：hooks.tick(frac) 為選配的「階段內進度＋讓步」鉤（見 §量化進度分塊）；
   雙料的逐格迴圈只有一次距離計算（實測 ≤0.1s），整段跑完回報一次即可。 */
async function quantizeDual(img, P, slots, hooks){
  const K=P.klevels;
  const A=hexLin(slots[0].color), B=hexLin(slots[1].color);
  const labF=t=> t>0.008856 ? Math.cbrt(t) : (7.787*t + 16/116);
  const labFinv=fy=> fy**3>0.008856 ? fy**3 : (fy-16/116)/7.787;
  const YA=lum709(...A), YB=lum709(...B);
  const LA=116*labF(YA)-16, LB=116*labF(YB)-16;
  const levels=[];
  for(let i=0;i<K;i++){
    const Lt=K<2?LA:LA+(LB-LA)*i/(K-1);
    const Yt=labFinv((Lt+16)/116);
    const t=Math.abs(YA-YB)<1e-9 ? 0 : Math.min(1,Math.max(0,(YA-Yt)/(YA-YB)));
    const lin=[0,1,2].map(c=>A[c]*(1-t)+B[c]*t);
    levels.push({t, lin, rgb:lin.map(l2s), lab:lin2lab(...lin)});
  }
  const n=img.w*img.h;
  const rawLabels=new Uint8Array(n);
  const spanL=LB-LA;
  for(let p=0;p<n;p++){
    const k=Math.abs(spanL)<1e-9 ? 0 : Math.round((img.lab[p*3]-LA)/spanL*(K-1));
    rawLabels[p]=Math.min(K-1,Math.max(0,k));
  }
  if (hooks && hooks.tick) await hooks.tick(1);
  return { rawLabels, palette: levels, filterStrategy: 'median' };
}

/* ================= 四料量化（index.html:376-437 計算部；畫布/清單拿掉） =================
   C-1 量化進度分塊：quad 的「格數×候選數」內積是全鏈最長段（C-0 §4.2：合法上限
   400×400・K=48 量化段 47.9–54.5s）。把逐格迴圈按「列區塊」切開，區塊之間
   await hooks.tick(frac)＝回報進度＋讓 cancel 指令被觀察到。
   ⚠ 迴圈順序、算式、寫入順序全部不變 ⇒ 標籤結果與 spike／工作室逐位元一致。 */
const QUANT_ROWS_PER_BLOCK = 64;
async function quantizeQuad(img, P, slots, hooks){
  const K=Math.max(2,P.klevels);
  const cols=slots.slice(0,4).map(s=>hexLin(s.color));
  const mixLin=w=>[0,1,2].map(ch=>(w[0]*cols[0][ch]+w[1]*cols[1][ch]+w[2]*cols[2][ch]+w[3]*cols[3][ch])/100);
  const PAIRS=[[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]];
  const cands=[]; const seenW=new Set();
  for(const [i,j] of PAIRS){
    for(let s=0;s<K;s++){
      const w=[0,0,0,0];
      w[i]=Math.round((1-s/(K-1))*100); w[j]=100-w[i];
      const key=w.join(','); if(seenW.has(key)) continue; seenW.add(key);
      const lin=mixLin(w);
      cands.push({w, lin, lab:lin2lab(...lin)});
    }
  }
  const n=img.w*img.h;
  let dropped=0;
  const assign=new Uint16Array(n); const usage=new Uint32Array(cands.length);
  for(let y0=0;y0<img.h;y0+=QUANT_ROWS_PER_BLOCK){
    const pEnd=Math.min(n,(y0+QUANT_ROWS_PER_BLOCK)*img.w);
    for(let p=y0*img.w;p<pEnd;p++){
      const L0=img.lab[p*3],A0=img.lab[p*3+1],B0=img.lab[p*3+2];
      let bi=0,bd=1e9;
      for(let i=0;i<cands.length;i++){ const c=cands[i].lab;
        const d=(L0-c[0])**2+(A0-c[1])**2+(B0-c[2])**2;
        if(d<bd){bd=d;bi=i;} }
      assign[p]=bi; usage[bi]++;
    }
    if (hooks && hooks.tick) await hooks.tick(Math.min(1, pEnd/n) * 0.9);   // 主迴圈佔本階段 90%
  }
  let used=[...cands.keys()].filter(i=>usage[i]>0).sort((a,b)=>usage[b]-usage[a]);
  const MAXP = P.pillar ? 63 : 64;   // 洗料柱佔 1 支（Orca 上限 64；index.html:411）
  if(used.length>MAXP){ dropped=used.length-MAXP; used=used.slice(0,MAXP); }
  used.sort((a,b)=>cands[b].lab[0]-cands[a].lab[0]);
  const remap=new Int16Array(cands.length).fill(-1);
  const palette=used.map((ci,pi)=>{ remap[ci]=pi; const c=cands[ci];
    return {w:c.w, lin:c.lin, lab:c.lab, rgb:c.lin.map(l2s)}; });
  const rawLabels=new Uint8Array(n);
  for(let p=0;p<n;p++){
    let pi=remap[assign[p]];
    if(pi<0){
      const L0=img.lab[p*3],A0=img.lab[p*3+1],B0=img.lab[p*3+2];
      let bd=1e9; pi=0;
      for(let i=0;i<palette.length;i++){ const c=palette[i].lab;
        const d=(L0-c[0])**2+(A0-c[1])**2+(B0-c[2])**2;
        if(d<bd){bd=d;pi=i;} }
    }
    rawLabels[p]=pi;
  }
  if (hooks && hooks.tick) await hooks.tick(1);
  return { rawLabels, palette, dropped, candidates:cands.length, filterStrategy: 'mode' };
}

/* ================= 平均色差診斷（index.html:512-520 / 458-461 的度量部） ================= */
function avgDeltaE(img, labels, palette){
  const n=img.w*img.h; let sumDE=0;
  for(let p=0;p<n;p++){
    const lab=palette[labels[p]].lab;
    const dl=img.lab[p*3]-lab[0], da=img.lab[p*3+1]-lab[1], db=img.lab[p*3+2]-lab[2];
    sumDE+=Math.sqrt(dl*dl+da*da+db*db);
  }
  return sumDE/n;
}

/* ================= 自動配色（index.html:783-878 垂直分支；DOM/renderSlots 拿掉） ================= */
function suggestSlots(img, mode){
  const tl=img.thumbLab, m=tl.length/3;
  const slotCount = mode==='quad' ? 4 : 2;
  const K=Math.min(9, slotCount*3);
  let cen=[];
  const byL=[...Array(m).keys()].sort((a,b)=>tl[a*3]-tl[b*3]);
  for(let i=0;i<K;i++){ const p=byL[Math.floor((i+0.5)/K*(m-1))];
    cen.push([tl[p*3],tl[p*3+1],tl[p*3+2]]); }
  let cnt=new Array(K).fill(0);
  for(let it=0;it<14;it++){
    const sum=cen.map(()=>[0,0,0,0]);
    for(let p=0;p<m;p++){
      let bi=0,bd=1e9;
      for(let i=0;i<K;i++){ const c=cen[i];
        const d=(tl[p*3]-c[0])**2+(tl[p*3+1]-c[1])**2+(tl[p*3+2]-c[2])**2;
        if(d<bd){bd=d;bi=i;} }
      sum[bi][0]+=tl[p*3]; sum[bi][1]+=tl[p*3+1]; sum[bi][2]+=tl[p*3+2]; sum[bi][3]++;
    }
    cen=cen.map((c,i)=> sum[i][3]? [sum[i][0]/sum[i][3],sum[i][1]/sum[i][3],sum[i][2]/sum[i][3]] : c);
    cnt=sum.map(s=>s[3]);
  }
  const clusters=cen.map((c,i)=>({lab:c,n:cnt[i]})).filter(c=>c.n>m*0.005);
  function lab2hex(lab){
    const fy=(lab[0]+16)/116, fx=fy+lab[1]/500, fz=fy-lab[2]/200;
    const inv=t=> t**3>0.008856 ? t**3 : (t-16/116)/7.787;
    const x=inv(fx)*0.95047, y=inv(fy), z=inv(fz)*1.08883;
    let r= 3.2406*x-1.5372*y-0.4986*z, g=-0.9689*x+1.8758*y+0.0415*z, b= 0.0557*x-0.2040*y+1.0570*z;
    return rgbHex(l2s(r),l2s(g),l2s(b));
  }
  if(slotCount===2){
    let main=null, bs=-1;
    for(const c of clusters){
      const ch=Math.hypot(c.lab[1],c.lab[2]);
      const s=Math.sqrt(c.n)*(ch+3);
      if(s>bs){bs=s;main=c;}
    }
    if(main && Math.hypot(main.lab[1],main.lab[2])<8)
      main=clusters.reduce((a,b)=>a.lab[0]<b.lab[0]?a:b);
    return [ {color:'#f2f0eb', td:6, start:1}, {color:lab2hex(main.lab), td:2, start:1} ];
  }
  /* 四料：色相家族（index.html:812-831）＋白底＋前三大家族深色代表（:873-878） */
  let pool=clusters.filter(c=>c.lab[0]<86);
  if(!pool.length) pool=clusters;
  const fams=[];
  for(const c of pool){
    const ch=Math.hypot(c.lab[1],c.lab[2]);
    const hue=Math.atan2(c.lab[2],c.lab[1]);
    let f=null;
    if(ch>=8){
      for(const q of fams){ if(q.ch<8)continue;
        let dh=Math.abs(hue-q.hue); if(dh>Math.PI)dh=2*Math.PI-dh;
        if(dh<0.7){f=q;break;} }
    }else f=fams.find(q=>q.ch<8)||null;
    const w=c.n*(1+ch/25);
    if(f){ f.w+=w; if(c.lab[0]<f.deep.lab[0])f.deep=c;
           f.sumL+=c.lab[0]*c.n; f.sumN+=c.n; }
    else fams.push({hue,ch,w,deep:c,sumL:c.lab[0]*c.n,sumN:c.n});
  }
  fams.sort((a,b)=>b.w-a.w);
  const top=fams.slice(0,3);
  while(top.length<3) top.push(top[top.length-1]);
  const slots=[{color:'#f2f0eb', td:6, start:1}];
  for(let i=0;i<3;i++) slots.push({color:lab2hex(top[Math.min(i,top.length-1)].deep.lab), td:2, start:1});
  return slots;
}

/* ================= ZIP（index.html:1049-1094 verbatim） ================= */
const CRC_TABLE=(()=>{ const t=new Uint32Array(256);
  for(let i=0;i<256;i++){ let c=i; for(let k=0;k<8;k++) c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1); t[i]=c; }
  return t; })();
function crc32(u8){ let c=0xFFFFFFFF;
  for(let i=0;i<u8.length;i++) c=CRC_TABLE[(c^u8[i])&0xFF]^(c>>>8);
  return (c^0xFFFFFFFF)>>>0; }
async function deflateRaw(u8){
  if(typeof CompressionStream==='undefined') return null;
  const cs=new CompressionStream('deflate-raw');
  return new Uint8Array(await new Response(new Blob([u8]).stream().pipeThrough(cs)).arrayBuffer());
}
async function makeZip(entries){
  const enc=new TextEncoder(); const chunks=[]; const central=[]; let offset=0;
  for(const e of entries){
    const nameB=enc.encode(e.name);
    const data= typeof e.data==='string' ? enc.encode(e.data) : e.data;
    const crc=crc32(data);
    let comp=await deflateRaw(data), method=8;
    if(!comp || comp.length>=data.length){ comp=data; method=0; }
    const lh=new DataView(new ArrayBuffer(30));
    lh.setUint32(0,0x04034b50,true); lh.setUint16(4,20,true);
    lh.setUint16(8,method,true);
    lh.setUint32(14,crc,true); lh.setUint32(18,comp.length,true); lh.setUint32(22,data.length,true);
    lh.setUint16(26,nameB.length,true);
    chunks.push(new Uint8Array(lh.buffer),nameB,comp);
    central.push({nameB,crc,clen:comp.length,rlen:data.length,method,offset});
    offset+=30+nameB.length+comp.length;
  }
  const cdStart=offset;
  for(const c of central){
    const ch=new DataView(new ArrayBuffer(46));
    ch.setUint32(0,0x02014b50,true); ch.setUint16(4,20,true); ch.setUint16(6,20,true);
    ch.setUint16(10,c.method,true);
    ch.setUint32(16,c.crc,true); ch.setUint32(20,c.clen,true); ch.setUint32(24,c.rlen,true);
    ch.setUint16(28,c.nameB.length,true);
    ch.setUint32(42,c.offset,true);
    chunks.push(new Uint8Array(ch.buffer),c.nameB);
    offset+=46+c.nameB.length;
  }
  const eo=new DataView(new ArrayBuffer(22));
  eo.setUint32(0,0x06054b50,true);
  eo.setUint16(8,central.length,true); eo.setUint16(10,central.length,true);
  eo.setUint32(12,offset-cdStart,true); eo.setUint32(16,cdStart,true);
  chunks.push(new Uint8Array(eo.buffer));
  return new Blob(chunks,{type:'model/3mf'});
}
function xmlEsc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ================= 3MF 組裝（index.html:1096-1257 verbatim；params→P、slots 注入） ================= */
async function build3mfFrom(P, img, labels, palette, noiseStats, extras){
  if (!root.PhotoTileMesh) throw new EngineError(ERR.MESH_MODULE_MISSING, '連通網格模組未載入');
  const mode=P.mode, noiseMm=P.noiseMm;
  const w=img.w,h=img.h;
  let L=new Uint8Array(labels);
  let teethFlips=0;
  if(P.teeth){
    const O=new Uint8Array(L);
    for(let y=1;y<h;y+=2)
      for(let x=1;x<w;x++)
        if(L[y*w+x-1]!==L[y*w+x]){ O[y*w+x]=L[y*w+x-1]; teethFlips++; }
    L=O;
  }
  const sx=P.width/w, sz=P.height/h, T=P.thick;
  const collected=root.PhotoTileMesh.collectParts(L,w,h,palette.length);
  const parts=collected.parts;
  let totalTiles=0,totalVertices=0,totalTriangles=0;
  const TRI=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[3,6,2],[3,7,6],[0,7,3],[0,4,7],[1,2,6],[1,6,5]];
  const f=v=>Math.round(v*1000)/1000;
  const objXml=[]; const cfgParts=[]; const palLines=[];
  const meshStats=[];
  /* V 溝已移除（Eric 2026-07-29 裁）；溝參數傳 null＝notchOn=false 原始碼路（index.html:1128-1133） */
  parts.forEach((part,pi)=>{
    const mesh=root.PhotoTileMesh.buildLabelMesh(L,w,h,part.k,part.runs,sx,sz,T,null);
    const V=mesh.vertices.map(v=>`<vertex x="${v[0]}" y="${v[1]}" z="${v[2]}"/>`);
    const VX=mesh.vertices;
    const OUTER_TOL=Math.max(0.01,sx/2);
    const F=mesh.triangles.map(t=>{
      const x0=VX[t[0]][0];
      if(Math.abs(x0-VX[t[1]][0])<1e-9 && Math.abs(x0-VX[t[2]][0])<1e-9){
        if(P.p2aBlock && (x0<OUTER_TOL || x0>P.width-OUTER_TOL))
          return `<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}"/>`;
        return `<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}" paint_seam="4"/>`;
      }
      const y0=VX[t[0]][1];
      const blk=(P.p2aBlock && Math.abs(y0-VX[t[1]][1])<1e-9 && Math.abs(y0-VX[t[2]][1])<1e-9) ? ' paint_seam="8"' : '';
      return `<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}"${blk}/>`;
    });
    totalTiles+=mesh.tiles; totalVertices+=V.length; totalTriangles+=F.length;
    meshStats.push({label:part.k,components:mesh.components,tiles:mesh.tiles,vertices:V.length,triangles:F.length});
    const oid=pi+1;
    objXml.push(`<object id="${oid}" type="model"><mesh><vertices>${V.join('')}</vertices><triangles>${F.join('')}</triangles></mesh></object>`);
    const pal=palette[part.k];
    const previewColor=rgbHex(...pal.rgb).toUpperCase();
    const name = mode==='quad'
      ? `零件色${pi+1} ${previewColor} A${pal.w[0]} B${pal.w[1]} C${pal.w[2]} D${pal.w[3]}`
      : `零件色${pi+1} ${previewColor} S${Math.round((1-pal.t)*100)/100}`;
    cfgParts.push(
      `    <part id="${oid}" subtype="normal_part">\n`+
      `      <metadata key="name" value="${xmlEsc(name)}"/>\n`+
      `      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n`+
      `      <metadata key="extruder" value="${pi+1}"/>\n`+
      `    </part>`);
    palLines.push( mode==='quad'
      ? `extruder ${pi+1} color ${previewColor} = M6052 A${pal.w[0]} B${pal.w[1]} C${pal.w[2]} D${pal.w[3]}`
      : `extruder ${pi+1} color ${previewColor} = M6051 S${Math.round((1-pal.t)*100)/100}`);
  });
  let pillarOid=0;
  if(P.pillar){
    const side=P.pillarXY, gap=15;
    pillarOid=parts.length+1;
    const X0=f(P.width+gap), X1=f(P.width+gap+side);
    const Y0=f(P.thick/2-side/2), Y1=f(P.thick/2+side/2);
    const Z0=0, Z1=f(P.height);
    const pv=[[X0,Y0,Z0],[X1,Y0,Z0],[X1,Y1,Z0],[X0,Y1,Z0],[X0,Y0,Z1],[X1,Y0,Z1],[X1,Y1,Z1],[X0,Y1,Z1]];
    const V=pv.map(v=>`<vertex x="${v[0]}" y="${v[1]}" z="${v[2]}"/>`).join('');
    const F=TRI.map(t=>`<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}"/>`).join('');
    objXml.push(`<object id="${pillarOid}" type="model"><mesh><vertices>${V}</vertices><triangles>${F}</triangles></mesh></object>`);
    const sourceLin=P.slots.slice(0,mode==='quad'?4:2).map(s=>hexLin(s.color));
    const pillarLin=[0,1,2].map(ch=>sourceLin.reduce((sum,c)=>sum+c[ch],0)/sourceLin.length);
    const pillarColor=rgbHex(...pillarLin.map(l2s)).toUpperCase();
    const pname = mode==='quad' ? `洗料柱 ${pillarColor} A25 B25 C25 D25` : `洗料柱 ${pillarColor} S0.5`;
    cfgParts.push(
      `    <part id="${pillarOid}" subtype="normal_part">\n`+
      `      <metadata key="name" value="${xmlEsc(pname)}"/>\n`+
      `      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n`+
      `      <metadata key="extruder" value="${pillarOid}"/>\n`+
      `      <metadata key="sparse_infill_density" value="100%"/>\n`+
      `    </part>`);
    palLines.push( mode==='quad'
      ? `extruder ${pillarOid} color ${pillarColor} = M6052 A25 B25 C25 D25（洗料柱 ${side}×${side}mm 實心方柱）`
      : `extruder ${pillarOid} color ${pillarColor} = M6051 S0.5（洗料柱 ${side}×${side}mm 實心方柱）`);
  }
  const MID=1000;
  const nObjs=parts.length+(pillarOid?1:0);
  const comps=Array.from({length:nObjs},(_,i)=>`<component objectid="${i+1}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>`).join('');
  const model=
`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <metadata name="Application">PING-PhotoTile-Prototype</metadata>
 <resources>
${objXml.map(o=>'  '+o).join('\n')}
  <object id="${MID}" type="model"><components>${comps}</components></object>
 </resources>
 <build><item objectid="${MID}" transform="1 0 0 0 1 0 0 0 1 ${f(-P.width/2)} ${f(-P.thick/2)} 0" printable="1"/></build>
</model>`;
  const cfg=
`<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="${MID}">
    <metadata key="name" value="${xmlEsc('照片磚')}"/>
${cfgParts.join('\n')}
  </object>
</config>`;
  const rels=`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>`;
  const types=`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="text/xml"/>
 <Default Extension="txt" ContentType="text/plain"/>
</Types>`;
  const palTxt=
`PING 照片磚 垂直多零件 配比表（${mode==='quad'?'四料 M6052':'雙料 M6051'}）
尺寸 ${P.width}x${P.height}x${P.thick} mm｜零件數 ${parts.length}${pillarOid?'＋洗料柱1':''}｜連通區 ${collected.components}｜網格片 ${totalTiles}｜三角形 ${totalTriangles}
口徑 ${P.nozzle} mm（水平最小色塊寬 ≥ ${(2*P.nozzle).toFixed(1)} mm，窄條已併入鄰色）
接縫：端面 paint_seam 標記（交界／側邊窄面）——縫拉往零件交界；接縫位置請用「對齊」（V 溝已於 2026-07-29 移除）；P2A 正背面禁縫=${P.p2aBlock?'開':'關'}
雜訊濾除 ${noiseMm>0?`尺寸 ≤ ${noiseMm.toFixed(1)} mm，已平滑／合併 ${noiseStats?noiseStats.changedPixels:0} 格，移除 ${noiseStats?noiseStats.removedComponents:0} 個小色塊（不留空洞）`:'關閉'}
${palLines.join('\n')}`;
  const entries=[
    {name:'[Content_Types].xml', data:types},
    {name:'_rels/.rels', data:rels},
    {name:'3D/3dmodel.model', data:model},
    {name:'Metadata/model_settings.config', data:cfg},
    {name:'Metadata/ping_palette.txt', data:palTxt},
  ];
  /* C-1 metadata＝opt-in（extras 缺席時本陣列與 C-0 spike／工作室完全相同
     ⇒ 3MF 位元組全等、黃金 oracle 續用）。schema 說明＝tools/ping/phototile_protocol.md §4 */
  if (extras && extras.metadataJson) {
    entries.push({name:'Metadata/ping_phototile.json', data:extras.metadataJson});
    if (extras.sourceImage && extras.sourceImage.bytes && extras.sourceImage.name)
      entries.push({name:'Metadata/'+extras.sourceImage.name, data:extras.sourceImage.bytes});
  }
  const blob=await makeZip(entries);
  return {blob, parts:parts.length, components:collected.components, tiles:totalTiles,
          vertices:totalVertices, triangles:totalTriangles, pillar:!!pillarOid, extruders:nObjs,
          meshStats, teethFlips};
}

/* ================= generate(request) → Promise<result> ================= */
let jobSeq = 0;
const activeJobs = new Map();

/* 階段間讓步＝MessageChannel macrotask（非 setTimeout＝不受隱形節流影響）：
   讓宿主 postMessage 送達的 cancel 能在階段邊界被觀察到（F-07 修正）。 */
const yieldMacro = () => new Promise(r => {
  const c = new MessageChannel();
  c.port1.onmessage = () => { c.port1.close(); r(); };
  c.port2.postMessage(0);
});

function cancel(jobId){
  const job = activeJobs.get(jobId);
  if (job) { job.cancelled = true; return true; }
  return false;
}

/* ================= palette DTO＝result 與 3MF metadata 的單一來源 ================= */
function paletteDto(palette, mode){
  return palette.map((pal,i)=> mode==='quad'
    ? { index:i+1, hex:rgbHex(...pal.rgb).toUpperCase(), recipe:{ gcode:'M6052', A:pal.w[0], B:pal.w[1], C:pal.w[2], D:pal.w[3] } }
    : { index:i+1, hex:rgbHex(...pal.rgb).toUpperCase(), recipe:{ gcode:'M6051', S:Math.round((1-pal.t)*100)/100 } });
}

/* SHA-256：優先用 crypto.subtle（快），沒有就用協定模組的純 JS 版。
   ⚠ **不得回傳 null**——宿主端把「沒有 digest」當協定錯誤處理（四項驗證不可有空門）。
   file:// 之類環境是否具備 subtle 因 runtime 而異，所以這裡不賭環境。 */
async function sha256Hex(bytes){
  if (root.crypto && root.crypto.subtle) {
    try {
      const d = await root.crypto.subtle.digest('SHA-256', bytes);
      return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,'0')).join('');
    } catch (e) { /* 落到後備 */ }
  }
  if (root.PhotoTileProtocol && root.PhotoTileProtocol.sha256HexSync)
    return root.PhotoTileProtocol.sha256HexSync(bytes);
  throw new EngineError(ERR.INTERNAL, 'SHA-256 不可用（crypto.subtle 與後備實作都缺席）');
}
function base64ToBytes(b64){
  const bin = atob(b64); const out = new Uint8Array(bin.length);
  for (let i=0;i<bin.length;i++) out[i] = bin.charCodeAt(i);
  return out;
}
const MIME_EXT = { 'image/png':'png', 'image/jpeg':'jpg', 'image/jpg':'jpg', 'image/webp':'webp', 'image/bmp':'bmp' };

/* ================= 最小 metadata schema（C 案裁決 6＝嵌原圖、save/reopen 續調） =================
   寫進 3MF 的 Metadata/ping_phototile.json；欄位契約＝tools/ping/phototile_protocol.md §4。
   只有 request.metadata 存在時才產生（opt-in＝黃金比對保命索）。 */
const METADATA_SCHEMA = 1;
async function buildExtras(P, q, filtered, palette, source, img){
  const md = P.metadata || {};
  const embedSource = md.embedSource !== false;               // 預設嵌原圖（裁決 6）
  let sourceImage = null, sourceMeta = null;
  if (source && source.base64) {
    const bytes = base64ToBytes(source.base64);
    const ext = MIME_EXT[source.mime] || 'bin';
    sourceMeta = { mime: source.mime, byteLength: bytes.length,
                   sha256: await sha256Hex(bytes), name: source.name || null,
                   embedded: embedSource, entry: embedSource ? ('Metadata/ping_phototile_source.'+ext) : null };
    if (embedSource) sourceImage = { name: 'ping_phototile_source.'+ext, bytes };
  } else {
    sourceMeta = { mime:null, byteLength:0, sha256:null, name:null, embedded:false, entry:null,
                   note:'呼叫端傳入已解碼影像（無原始位元組）＝不可嵌入' };
  }
  const metadata = {
    schema: METADATA_SCHEMA,
    engine: ENGINE_VERSION,
    groupUuid: md.groupUuid || null,                          // 物件身分（C-2 原子替換用；由 C++ 產生）
    createdBy: md.createdBy || 'PING-PhotoTile',
    mode: P.mode,
    nozzle: P.nozzle,
    canonical: { widthMm: P.width, heightMm: P.height, thickMm: P.thick },  // 引擎產出的幾何尺寸
    params: { klevels: P.klevels, noiseMm: P.noiseMm,
              pillar: { enabled: P.pillar, xyMm: P.pillarXY },
              seam: { teeth: P.teeth, p2aBlock: P.p2aBlock },
              limits: P.limits },
    slots: P.slots,
    palette,                                                  // index → hex → M6051/M6052 配比
    sourceImage: sourceMeta,
    env: P.env,                                               // 生成當下的環境快照（供追溯，不是驗證來源）
    stats: { gridW: img ? img.w : null, gridH: img ? img.h : null,
             dropped: q.dropped || 0, candidates: q.candidates || 0, noise: filtered.stats }
  };
  return { metadata, metadataJson: JSON.stringify(metadata, null, 2), sourceImage };
}

/* 階段權重（C-0 §4.1/§4.2 實測時間佔比；只用來換算對使用者顯示的百分比） */
const STAGE_WEIGHT = { decode:0.02, grid:0.10, suggest:0.03, quantize:0.45, filter:0.25, metric:0.03, mesh:0.12 };
const STAGE_ORDER  = ['decode','grid','suggest','quantize','filter','metric','mesh'];
const STAGE_LABEL  = { decode:'解碼影像', grid:'建立格點', suggest:'自動配色', quantize:'色階量化',
                       filter:'雜訊濾除與最小寬度', metric:'色差評估', mesh:'產生網格與 3MF' };
function stageBase(stage){
  let acc = 0;
  for (const s of STAGE_ORDER) { if (s === stage) break; acc += STAGE_WEIGHT[s]; }
  return acc;
}

async function generate(request, options){
  const t0 = performance.now();
  let P;
  try { P = normalizeRequest(request); }
  catch (e) {
    return { jobId: request && request.jobId || null, ok:false,
             error:{ code: e.code || ERR.BAD_REQUEST, message: e.message } };
  }
  const job = { cancelled:false };
  activeJobs.set(P.jobId, job);
  const timings = {};
  /* 引擎自己解碼出來的 ImageBitmap 一定要關，**不管這個 job 怎麼結束**。
     原本只在成功路徑的 grid 之後關（見下方 own 註解），取消或任何階段丟例外都會漏掉——
     48M 像素的圖漏一張就是幾百 MB，連續取消幾次就爆（Codex 重要 #11）。
     用 finally 兜底：ownedBitmap 在 resolveImage 之後登記，關過就清掉不重複關。 */
  let ownedBitmap = null;
  const releaseOwnedBitmap = () => {
    if (ownedBitmap && typeof ownedBitmap.close === 'function') {
      try { ownedBitmap.close(); } catch (e) { /* 已關過／不支援：忽略 */ }
    }
    ownedBitmap = null;
  };
  const ck = stage => { if (job.cancelled) throw new EngineError(ERR.CANCELLED, '已取消（' + stage + '）'); };
  /* 進度回報：宿主給 onProgress 才回報；回報本身不得引入計時器（§零計時器紀律） */
  const onProgress = options && typeof options.onProgress === 'function' ? options.onProgress : null;
  const report = (stage, frac) => {
    if (!onProgress) return;
    const pct = Math.max(0, Math.min(1, stageBase(stage) + STAGE_WEIGHT[stage] * Math.max(0, Math.min(1, frac))));
    try { onProgress({ jobId: P.jobId, stage, stageLabel: STAGE_LABEL[stage], pct,
                       elapsedMs: performance.now() - t0 }); } catch (e) { /* 進度回報失敗不影響生成 */ }
  };
  /* 階段內的分塊鉤：回報 → 讓步（MessageChannel）→ 檢查取消 */
  const hooksFor = stage => ({ tick: async frac => { report(stage, frac); await yieldMacro(); ck(stage); } });
  try {
    if (!root.PhotoTileMesh) throw new EngineError(ERR.MESH_MODULE_MISSING, '連通網格模組未載入');
    let t = performance.now();
    report('decode', 0);
    const resolved = await resolveImage(P.image, P.limits);
    const bitmap = resolved.bitmap;
    if (resolved.owned) ownedBitmap = bitmap;      // 從這一刻起，finally 保證會關
    timings.decodeMs = performance.now() - t;  report('decode', 1); await yieldMacro(); ck('decode');

    t = performance.now();
    const img = buildGridData(bitmap, P.width, P.height, P.limits.gridMax);
    /* 格點建完，解碼後的點陣圖就沒用了。**引擎自己解碼的才關**（呼叫端傳進來的
       ImageBitmap 屬於呼叫端，關掉會害它下一案沒圖——黃金 runner 就是重複使用同一張）。
       高像素輸入時這一關就是幾百 MB 的差別（C-0 §4.3：真壓力在 decoded bitmap）。 */
    releaseOwnedBitmap();
    timings.gridMs = performance.now() - t;    report('grid', 1); await yieldMacro(); ck('grid');

    if (!P.slots) P.slots = suggestSlots(img, P.mode);          // 自動配色（工作室「開圖即建議」等價）
    report('suggest', 1); await yieldMacro(); ck('suggest');

    t = performance.now();
    const q = P.mode === 'quad' ? await quantizeQuad(img, P, P.slots, hooksFor('quantize'))
                                : await quantizeDual(img, P, P.slots, hooksFor('quantize'));
    timings.quantizeMs = performance.now() - t; report('quantize', 1); await yieldMacro(); ck('quantize');

    t = performance.now();
    const filtered = filterLabels(q.rawLabels, img, P, q.palette.length, q.filterStrategy);
    timings.filterMs = performance.now() - t;  report('filter', 1); await yieldMacro(); ck('filter');

    const deltaE = avgDeltaE(img, filtered.labels, q.palette);
    report('metric', 1); await yieldMacro(); ck('metric');

    const palette = paletteDto(q.palette, P.mode);
    const extras = P.metadata ? await buildExtras(P, q, filtered, palette, resolved.source, img) : null;

    t = performance.now();
    report('mesh', 0);
    const built = await build3mfFrom(P, img, filtered.labels, q.palette, filtered.stats, extras);
    timings.meshZipMs = performance.now() - t; report('mesh', 1); ck('mesh');

    const bytes = new Uint8Array(await built.blob.arrayBuffer());
    timings.totalMs = performance.now() - t0;

    return {
      jobId: P.jobId, ok: true,
      env: P.env,                                  // 環境快照原封回傳（C++ 比對過期即棄）
      metadata: extras ? extras.metadata : null,   // 與 3MF 內 ping_phototile.json 同源
      limits: P.limits,
      fileName: '照片磚_連通網格版.3mf',
      threeMF: bytes, blob: built.blob, byteLength: bytes.length,
      mode: P.mode, nozzle: P.nozzle,
      palette,
      slots: P.slots,
      stats: { gridW: img.w, gridH: img.h, parts: built.parts, components: built.components,
               tiles: built.tiles, vertices: built.vertices, triangles: built.triangles,
               extruders: built.extruders, pillar: built.pillar,
               dropped: q.dropped || 0, candidates: q.candidates || 0 },
      diagnostics: { noise: filtered.stats, teethFlips: built.teethFlips, avgDeltaE: deltaE,
                     clamped: P.clamped, timings, meshStats: built.meshStats }
    };
  } catch (e) {
    const code = e instanceof EngineError ? e.code : ERR.INTERNAL;
    return { jobId: P.jobId, ok:false, error:{ code, message: e && e.message || String(e) },
             diagnostics: { timings } };
  } finally {
    releaseOwnedBitmap();                        // 取消／例外／早退都走這裡
    activeJobs.delete(P.jobId);
  }
}

return { generate, cancel, suggestSlots, gridDims, sha256Hex, ERR,
         version: ENGINE_VERSION,
         metadataSchema: METADATA_SCHEMA,
         limitsDefault: { gridMax: GRID_MAX, maxDecodedPixels: 0 },
         _internals: { buildGridData, quantizeDual, quantizeQuad, filterLabels, build3mfFrom, paletteDto } };
});
