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
     ① progress 回報（階段權重＋量化熱迴圈分塊回報；合法上限案 quad K8 ≈20 秒【K 上限 8＝Eric 0802 裁 B】）
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
    thick:  clamp('thick',  size.thickMm,  2, 30, 10),                       // index.html:1014-1016
    /* 上限 48→8＝Eric 2026-08-02 裁 B。依據：①他實測雙料 8 階已偏多、6 階足夠
       ②K 掃描實證最終調色盤有 64 色上限，K≥11 之後色數完全不變、只是白燒 quantize
       （K48 比 K12 慢 3.3 倍、零色數收益；ksweep_result_20260802.json）。
       同值另住 index.html 的輸入框 max 與 clamp——改要一起改。 */
    klevels: Math.round(clamp('klevels', req.klevels, 2, 8, 8)),
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
    // 二輪 M15：先存尺寸再 close——close 後 width/height 歸零，錯誤訊息永遠顯示 0×0
    const W = bmp.width, H = bmp.height, got = W * H;
    if (typeof bmp.close === 'function') bmp.close();
    throw new EngineError(ERR.IMAGE_TOO_LARGE,
      `影像 ${W}×${H}＝${(got/1e6).toFixed(1)}M 像素，超過上限 ${(cap/1e6).toFixed(1)}M 像素`);
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

/* ================= 最小可印寬度：2-D 形態學開運算（2026-08-15 新增・Eric 裁 P0） =========
   為什麼需要：`enforceMinHorizontalWidth` 只守水平、`filterSmallComponents` 只殺孤島，
   於是「附著在大塊上的細長突起」兩關都過（實錄：杜賓剪影的耳緣碎塊、尾巴細線、
   腿部斑紋鋸齒邊）。開運算 erode→dilate 才是「窄於 N 就消失」的正確語意。

   ⚠ 先前試過的錯解：把標籤圖轉置後重跑 enforceMinHorizontalWidth。那支函式併掉的是
      「短於門檻的**段**」，而圓形色塊的上下左右邊緣天生就是短段 ⇒ 兩向各跑一次＝
      從四面侵蝕，**杜賓的眼睛整個被磨掉**。兩道 1-D 掃描 ≠ 2-D 開運算，而且比它兇。

   做法（**與色數無關**，四料最多 64 色也不會變慢）：
     ① 逐格算「以它為中心的矩形窗內有沒有任何標籤邊界」＝ uniform（＝侵蝕的結果，
        因為窗內無邊界 ⟺ 窗內全同一標籤）。用「水平邊界」「垂直邊界」兩張積分圖 O(1) 查詢。
     ② survives ＝ 對 uniform 再做一次窗內求和 >0（＝膨脹）。能被任何一個 uniform 窗
        覆蓋到的格就夠寬——而覆蓋它的窗必然與它同標籤，所以不需要逐色階分開算。
     ③ 沒通過的格清空，再用多源 BFS 從通過的格就近回填（4-連通＝曼哈頓最近標籤）。
   複雜度＝3 次積分圖建置＋2 次掃描，O(w·h)。 */
function openLabelsMinWidth(labels, w, h, wx, wy){
  const n=w*h, rx=(wx-1)>>1, ry=(wy-1)>>1;
  if(rx<1 && ry<1) return { labels:new labels.constructor(labels), openedAway:0 };
  const W1=w+1, IH=new Int32Array(W1*(h+1)), IV=new Int32Array(W1*(h+1));
  for(let y=0;y<h;y++){
    const r=y*w, o=(y+1)*W1, o0=y*W1; let rh=0, rv=0;
    for(let x=0;x<w;x++){
      const p=r+x;
      if(x<w-1 && labels[p]!==labels[p+1]) rh++;
      if(y<h-1 && labels[p]!==labels[p+w]) rv++;
      IH[o+x+1]=IH[o0+x+1]+rh; IV[o+x+1]=IV[o0+x+1]+rv;
    }
  }
  const q=(I,x0,y0,x1,y1)=> (x1<x0||y1<y0) ? 0 :
    I[(y1+1)*W1+x1+1]-I[y0*W1+x1+1]-I[(y1+1)*W1+x0]+I[y0*W1+x0];
  const uni=new Uint8Array(n);
  for(let y=0;y<h;y++){
    const y0=Math.max(0,y-ry), y1=Math.min(h-1,y+ry), r=y*w;
    for(let x=0;x<w;x++){
      const x0=Math.max(0,x-rx), x1=Math.min(w-1,x+rx);
      if(q(IH,x0,y0,x1-1,y1)===0 && q(IV,x0,y0,x1,y1-1)===0) uni[r+x]=1;
    }
  }
  IH.fill(0);
  for(let y=0;y<h;y++){
    const r=y*w, o=(y+1)*W1, o0=y*W1; let row=0;
    for(let x=0;x<w;x++){ row+=uni[r+x]; IH[o+x+1]=IH[o0+x+1]+row; }
  }
  const out=new labels.constructor(labels), assigned=new Uint8Array(n);
  const queue=new Int32Array(n); let qt=0;
  for(let y=0;y<h;y++){
    const y0=Math.max(0,y-ry), y1=Math.min(h-1,y+ry), r=y*w;
    for(let x=0;x<w;x++){
      const x0=Math.max(0,x-rx), x1=Math.min(w-1,x+rx);
      if(q(IH,x0,y0,x1,y1)>0){ assigned[r+x]=1; queue[qt++]=r+x; }
    }
  }
  const openedAway=n-qt;
  if(qt===0) return { labels: out, openedAway: 0 };   // 全被開掉＝門檻不合理，原樣退回
  let qh=0;
  while(qh<qt){
    const p=queue[qh++], c=p%w;
    if(c>0   && !assigned[p-1]){ assigned[p-1]=1; out[p-1]=out[p]; queue[qt++]=p-1; }
    if(c<w-1 && !assigned[p+1]){ assigned[p+1]=1; out[p+1]=out[p]; queue[qt++]=p+1; }
    if(p>=w  && !assigned[p-w]){ assigned[p-w]=1; out[p-w]=out[p]; queue[qt++]=p-w; }
    if(p+w<n && !assigned[p+w]){ assigned[p+w]=1; out[p+w]=out[p]; queue[qt++]=p+w; }
  }
  return { labels: out, openedAway };
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
  /* 【2026-08-15・Eric 裁 P0】補上 2-D 開運算，解掉「附著在大塊上的細長突起」
     （水平向已由 enforceMinHorizontalWidth 處理，這一步接手垂直與斜向）。
     ⚠ **順序很重要：必須放在 filterSmallComponents 之後。**
        放前面會這樣壞事——開運算切斷「眼睛↔眉毛」之間的細橋後，眼睛變成孤立連通塊，
        而杜賓的眼睛約 2.1×1.95 mm、剛好卡在 noiseMm 2.0 mm 門檻邊緣 ⇒ 被當雜訊清掉。
        實錄：先放前面時杜賓兩隻眼睛整個消失（前後差異圖量到兩塊 41×39 格的移除）。
        放後面則雜訊濾除看到的是原本的連通性，眼睛保得住，開運算再去修細橋與毛刺。 */
  const opened=openLabelsMinWidth(result.labels,img.w,img.h,
    Math.max(1,Math.round(minWidthMm/sx)), Math.max(1,Math.round(minWidthMm/sz)));
  let changedPixels=0;
  for(let i=0;i<labels.length;i++) if(opened.labels[i]!==labels[i]) changedPixels++;
  const stats={removedComponents:result.removedComponents, changedPixels,
    smoothedPixels:smooth.changedPixels, changedAreaMm2:changedPixels*sx*sz,
    widthChangedPixels:wide.changedPixels, widthMergedRuns:wide.mergedRuns, minWidthMm,
    openedAwayPixels:opened.openedAway,
    passes:result.passes, thresholdMm:result.thresholdMm, strategy:smooth.strategy};
  return { labels: opened.labels, stats };
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
    /* 【2026-08-15 修・Eric 裁 P0】原評分＝√n×(彩度+3)，**沒有任何明度分離項**：
       第二支料只要「面積大又有彩度」就贏，於是四種題材實測全挑錯——
         人像原照 → 米白＋淡粉 #eab6a3（ΔE 28.5，整張糊成粉紅）
         臉填滿畫面的模板風 → 兩支米白（38.17，等於白板）
         風景剪影（大面積天空）→ 兩支米白（30.40）
         黑色杜賓 → 米白＋棕 #975a30（13.95，黑狗被印成棕狗）
       共同觸發條件＝**單一顏色佔大面積**。雙料的每一階都落在兩支料的連線上，
       兩支太接近＝整張磚根本沒有對比可用。
       ⚠ 遵守 Eric 2026-08-05 裁示「**分散是最佳化目標，不是閘門**」：
          這裡加的是**評分權重**（隨明度差飽和的係數），**不是硬門檻**——
          全圖真的只有淺色時仍會回傳相對最好的那一支，不會失敗；
          使用者手動指定相近色（同色系漸層）完全不受影響，
          本函式只約束「我們主動建議的初值」。 */
    const LA=lin2lab(...hexLin('#f2f0eb'))[0];   // slotA 固定米白，取其 L
    let main=null, bs=-1;
    for(const c of clusters){
      const ch=Math.hypot(c.lab[1],c.lab[2]);
      /* sep 刻意**不設飽和上限**：雙料的每一階都在兩支料的連線上，
         第二支越遠、整條可用色階越長，所以「更暗」要能持續加分。
         實證＝黑白杜賓：黑(ΔL≈80) 與棕斑(ΔL≈50) 若都夾成 1，就只剩彩度決勝，
         棕斑贏 ⇒ 黑狗被印成棕狗（ΔE 13.96，強制米白＋黑只要 8.46）。 */
      const sep=Math.abs(c.lab[0]-LA)/100;
      /* 彩度降為次要因子，與四料分支的 `1+彩度/25` 同一把尺（原本 `彩度+3`
         讓有彩度的群大贏 11 倍，才會發生「彩度壓過明度」的誤選）。
         保留「偏好有彩度」的既有取向，只是不再讓它一票否決明度。 */
      const s=Math.sqrt(c.n)*(1+ch/25)*sep;
      if(s>bs){bs=s;main=c;}
    }
    if(main && Math.hypot(main.lab[1],main.lab[2])<8)
      main=clusters.reduce((a,b)=>a.lab[0]<b.lab[0]?a:b);
    return [ {color:'#f2f0eb', td:6, start:1}, {color:lab2hex(main.lab), td:2, start:1} ];
  }
  /* 四料：白底＋三支從分群直接取的彩色。
     【2026-08-05 建議配色核心規格・Eric 裁「白＋不得複製充數」】
     舊法＝色相家族（index.html:812-831）→ 取前三大家族的 deep（最深那顆），不足三族就
       `while(top.length<3) top.push(top[top.length-1]);`
     兩個缺陷，都有實測（quad／400×400mm／格點 3200²／0.125mm 格）：
       ①**複製充數**：人物照通常只有「膚色」「消色」兩族 ⇒ 第 3、4 槽吐出逐字元相同的 hex
         （#2e231c ×2）＝四料當三料用，色數只有 19、整張灰。
       ②**永遠取 deep**＝四支全擠在暗端，中間調毫無代表。
     手動換成「白＋中間膚色＋深棕＋近黑」（互異且有中間調）⇒ 色數 36、ΔE 6.789→6.251，
     效益是調 K（8→14 只換到 0.044）的約 12 倍。
     新法＝直接在**分群層**做最遠點取樣（farthest-point）：
       種子＝權重最大的群（沿用原 w＝n×(1+彩度/25)，保留「偏好有彩度」的既有取向）；
       之後每次挑「離已選集合最遠」的群，距離用 Lab 歐氏＝與量化端指派同一把尺
       （engine.js 的最近鄰與 avgDeltaE 都是 Lab 歐氏，規格的尺與量化的尺必須同一把）。
     一招解兩病：不同的群天生不會給出同一個顏色；最遠點會自動把中間調納進來。
     ⚠ **分散是最佳化目標，不是閘門**（Eric 0805 追加澄清）——本函式不設「任兩支必須差多少」
       的硬門檻，使用者要刻意選兩支相近色（例如同色系漸層）照樣可以。本規格只約束
       「我們主動建議時給的初值」，不約束使用者。 */
  let pool=clusters.filter(c=>c.lab[0]<86);
  if(!pool.length) pool=clusters;
  const picks=[];
  if(pool.length){
    let seed=pool[0], sw=-1;
    for(const c of pool){
      const w=c.n*(1+Math.hypot(c.lab[1],c.lab[2])/25);
      if(w>sw){ sw=w; seed=c; }
    }
    picks.push(seed);
    while(picks.length<3 && picks.length<pool.length){
      let best=null, bd=-1;
      for(const c of pool){
        if(picks.indexOf(c)>=0) continue;
        let md=1e9;
        for(const p of picks){
          const d=Math.hypot(c.lab[0]-p.lab[0], c.lab[1]-p.lab[1], c.lab[2]-p.lab[2]);
          if(d<md) md=d;
        }
        if(md>bd){ bd=md; best=c; }
      }
      if(!best) break;
      picks.push(best);
    }
  }
  /* 群數不足三（極單調的圖）：**不複製**——沿用色相、把亮度推到還沒被佔用的一側，
     產生一支真的不一樣的補色。這是誠實的退化（該支確實不是從圖上萃取的），不是拿同一支充數。 */
  const labs=picks.map(c=>c.lab.slice());
  while(labs.length<3){
    const base=labs.length ? labs[labs.length-1] : [50,0,0];
    const used=labs.length ? labs.map(l=>l[0]) : [50];
    const L=(Math.max.apply(null,used)<50) ? Math.min(85, Math.max.apply(null,used)+28)
                                           : Math.max(12, Math.min.apply(null,used)-28);
    labs.push([L, base[1], base[2]]);
  }
  const slots=[{color:'#f2f0eb', td:6, start:1}];
  for(let i=0;i<3;i++) slots.push({color:lab2hex(labs[i]), td:2, start:1});
  /* 最後一道保險：不論如何都不得吐出兩支逐字元相同的 hex（不同的 Lab 也可能捨入到同一個
     hex）。真撞到就把亮度再推開，最多試 8 次（有界，避免病態圖造成無窮迴圈）。 */
  for(let i=1;i<slots.length;i++){
    let guard=0;
    while(guard++<8 && slots.slice(1,i).some(function(s){ return s.color===slots[i].color; })){
      labs[i-1][0]=Math.max(8, Math.min(92, labs[i-1][0] + (labs[i-1][0]>50 ? -9 : 9)));
      slots[i].color=lab2hex(labs[i-1]);
    }
  }
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
/* 分段 CRC：與 crc32() 同一張表、同一條公式，只是允許跨多段累積——
   為了讓 entry 的內容可以是「字串陣列」而不必先合成單一巨串（V8 字串上限 ~512MB；
   2026-08-03 閘門③ 48Mpx×fullgrid 案實撞「Invalid string length」＝model XML 過大）。 */
function crc32Pieces(pieces){
  let c=0xFFFFFFFF;
  for(const u8 of pieces)
    for(let i=0;i<u8.length;i++) c=CRC_TABLE[(c^u8[i])&0xFF]^(c>>>8);
  return (c^0xFFFFFFFF)>>>0;
}
async function deflateRawPieces(pieces){
  if(typeof CompressionStream==='undefined') return null;
  const cs=new CompressionStream('deflate-raw');
  // Blob 接受分段來源＝全程不存在單一 JS 巨串/巨陣列的合成點
  return new Uint8Array(await new Response(new Blob(pieces).stream().pipeThrough(cs)).arrayBuffer());
}
async function makeZip(entries, tick){
  /* tick（可選）＝每個 entry 壓縮前讓步＋看一次取消旗標（C-1 #11 後半，Eric 裁 C）。
     只在 entry 邊界讓步、完全不動 deflate 本身 ⇒ 輸出位元組與原版逐位元相同。
     e.data 可為：字串｜Uint8Array｜**字串/Uint8Array 陣列**（大 XML 分段用；位元組等價）。 */
  const enc=new TextEncoder(); const chunks=[]; const central=[]; let offset=0;
  for(const e of entries){
    if(tick) await tick();
    const nameB=enc.encode(e.name);
    const raw = Array.isArray(e.data) ? e.data : [e.data];
    const pieces = raw.map(p => typeof p==='string' ? enc.encode(p) : p);
    let rlen=0; for(const p of pieces) rlen+=p.length;
    const crc=crc32Pieces(pieces);
    let comp=await deflateRawPieces(pieces), method=8;
    let stored=null;
    /* ⚠ fallback 必須把 comp 清掉（Codex 二輪 B2）：0803 首版只設 stored/method、comp 留著
       ⇒ 下面 clen 取到 deflate 長度、chunks 塞進 deflate bytes，但 header 寫 method=0
       ＝自相矛盾的壞 ZIP。原版 index.html 的 `comp=data` 重指派本來是安全的，是我改壞的。
       黃金五輪沒炸純因現有 entries 全可壓縮、這條路從未走到——高熵內嵌圖（JPEG/亂數 PNG）就會中。 */
    if(!comp || comp.length>=rlen){ stored=pieces; method=0; comp=null; }
    const clen = comp ? comp.length : rlen;
    const lh=new DataView(new ArrayBuffer(30));
    lh.setUint32(0,0x04034b50,true); lh.setUint16(4,20,true);
    lh.setUint16(8,method,true);
    lh.setUint32(14,crc,true); lh.setUint32(18,clen,true); lh.setUint32(22,rlen,true);
    lh.setUint16(26,nameB.length,true);
    chunks.push(new Uint8Array(lh.buffer),nameB);
    if(comp) chunks.push(comp); else chunks.push(...stored);
    central.push({nameB,crc,clen,rlen,method,offset});
    offset+=30+nameB.length+clen;
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

/* ================= 3MF 組裝（index.html:1096-1257 verbatim；params→P、slots 注入） =================
   【C-1 #11 後半・Eric 2026-08-02 裁 C＝只修 mesh 段】實測取消落在本段要等 17.6 秒
   （最重合法案；cancellat_report_20260802.json）——本段原本從頭到尾零讓步點。
   修法與 quantizeQuad 同款：hooks.tick＝回報進度＋讓步＋檢查取消。讓步只加在
   「零件迴圈每 4 件」與「zip 每個 entry 之間」，**迴圈順序、算式、字串組裝完全不變**
   ⇒ 輸出位元組逐位元相同（黃金閘門複驗把關）。hooks 缺席＝行為與原版完全一致。 */
async function build3mfFrom(P, img, labels, palette, noiseStats, extras, hooks){
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
  /* V 溝已移除（Eric 2026-07-29 裁）；溝參數傳 null＝notchOn=false 原始碼路（index.html:1128-1133）
     forEach→for：迴圈體一字未動，只為了能在零件之間 await（forEach 的 callback 不能 await）。 */
  for(let pi=0;pi<parts.length;pi++){
    const part=parts[pi];
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
    // 每 4 件讓步一次：K48 重案 ~250 件⇒~60 個讓步點；dual K6 只有 6 件⇒開銷趨近零
    if(hooks && hooks.tick && (pi&3)===3) await hooks.tick(0.05+0.75*(pi+1)/parts.length);
  }
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
  /* 【2026-08-03】model XML 改「分段」而不合成單一字串：48Mpx×fullgrid 案的 XML 逼近
     V8 字串上限（~512MB），昨天 K48 險過、今天 K8 實撞「Invalid string length」＝
     這個案一直在懸崖邊滑冰。分段序列與原本的樣板字串**逐位元組等價**：
     原式＝objXml.map(o=>'  '+o).join('\n') 後接樣板換行 ⇒ 每個 objXml 項恰好
     「兩空格＋內容＋\n」一次；黃金閘門把關等價性。 */
  const modelPieces=[
`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <metadata name="Application">PING-PhotoTile-Prototype</metadata>
 <resources>
`];
  for(const o of objXml) modelPieces.push('  '+o+'\n');
  modelPieces.push(
`  <object id="${MID}" type="model"><components>${comps}</components></object>
 </resources>
 <build><item objectid="${MID}" transform="1 0 0 0 1 0 0 0 1 ${f(-P.width/2)} ${f(-P.thick/2)} 0" printable="1"/></build>
</model>`);
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
    {name:'3D/3dmodel.model', data:modelPieces},   // 分段（位元組等價，見上）
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
  const blob=await makeZip(entries, hooks && hooks.tick ? (()=>hooks.tick(0.9)) : null);
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
    // hooksFor('mesh')＝零件間與 zip entry 間可取消（Eric 2026-08-02 裁 C；#11 後半）
    const built = await build3mfFrom(P, img, filtered.labels, q.palette, filtered.stats, extras, hooksFor('mesh'));
    timings.meshZipMs = performance.now() - t; report('mesh', 1); ck('mesh');

    const bytes = new Uint8Array(await built.blob.arrayBuffer());
    ck('mesh');   // 二輪 I6：arrayBuffer 的 await 是 zip 後第一個讓步點，取消要在這裡被看到
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
         _internals: { buildGridData, quantizeDual, quantizeQuad, filterLabels, build3mfFrom, paletteDto,
                       makeZip /* 二輪 B2：讓 zip fallback 可被直接測（node 高熵案） */ } };
});
