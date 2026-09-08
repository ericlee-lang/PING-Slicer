/* PING 選機頁「認識列印模式」說明區（v12 定案・Eric 2026-09-08「好，定案」）
   定案交接＝00治理文件旁 `slides/generated/printer-mode-applications-20260908/HANDOFF-CLAUDE.md`。
   ─ 文案：由 mode-copy.json 機器產生（build_pingmodes.py），四語 zh_TW／en／de_DE／fr_FR；
     語言判定與 text.js 的 TranslatePage() 同一條：?lang= → localStorage → zh_CN 落 zh_TW → 缺就 en。
   ─ 圖：../ping-modes/<id>.png（v12 八張 *-cis.png 成品等比縮成 2x 密度；方 640、橫 840）。
   ─ 行為：頁籤只切換說明，不動任何機型勾選／搜尋／確定取消；預設頁籤＝雙料。
   ─ 掛點：HandleModelList() 組 PING 廠牌區塊時呼叫 PingModeHelpHtml('PING') 放在卡片區上方，
     區塊落地後呼叫 PingModeHelpInit() 渲染（冪等，重呼叫只重繪）。
   ─ 21 與 24 兩頁共用本檔；改文案改 mode-copy.json 再重產，不要手改下面的 JSON。 */

var PingModeCopy = {
 "zh_TW": {
  "lang": "zh-Hant",
  "heading": "認識列印模式",
  "selectMode": "選擇要查看說明的列印模式",
  "modes": {
   "dual": {
    "name": "雙料",
    "title": "A / B 雙料模式",
    "benefit": "兩支材料，個別設定",
    "body": "可用於雙色、異材質、軟硬結合，或分開列印主體與易拆支撐。",
    "limit": "",
    "alt": "雙料模式的三種用途：易拆支撐、雙色列印與軟硬結合。",
    "applications": [
     {
      "id": "dual-support",
      "label": "易拆支撐",
      "alt": "橘色電鑽半邊外殼斜放，開口朝上；灰色支撐格柵以連接底座與橫向連結托住弧形外殼、握把及底座下方的懸空處。"
     },
     {
      "id": "dual-color",
      "label": "雙色列印",
      "alt": "橘色外環與灰色中心直接相接，構成同一件雙色齒輪。"
     },
     {
      "id": "dual-soft",
      "label": "軟硬結合",
      "alt": "灰色軟質握把包覆並接合橘色硬質本體，形成一件完整產品。"
     }
    ]
   },
   "cofeed": {
    "name": "同進",
    "title": "同進模式",
    "benefit": "高流量・混色漸層・照片磚",
    "body": "兩卷同種材料：同色提高流量；不同色可隨列印高度改變混色比例，或製作照片磚。",
    "limit": "",
    "alt": "同進的三種用途：提高流量、混色漸層與照片磚。",
    "applications": [
     {
      "id": "cofeed",
      "label": "流量 ×2・速度 ×2",
      "alt": "兩卷橘色同種材料匯流後主線加粗並標示 ×2，列印橘色零件。"
     },
     {
      "id": "cofeed-gradient",
      "label": "混色漸層",
      "alt": "灰色與橘色兩卷同種材料匯流；無外框的成品由下方灰色平滑過渡至上方橘色，沒有內部分隔線，表示混色比例隨高度連續改變。"
     },
     {
      "id": "photo",
      "label": "照片磚（開發中）",
      "alt": "照片磚功能開發中。照片轉換為直立列印的照片磚，以混色呈現圖像。"
     }
    ]
   },
   "single": {
    "name": "單料頭",
    "title": "單料頭模式",
    "benefit": "一種材料・一卷即可",
    "body": "適合列印量較少、只有一卷材料，或不需同進額外流量的情境。",
    "limit": "",
    "alt": "一卷橘色材料供料，列印橘色的單一材料零件。"
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "主材流量 ×3・獨立易拆支撐",
    "body": "三支主材合流列印主體，第四支材料獨立列印懸空面下方的支撐。",
    "limit": "",
    "alt": "三卷橘色主材線合流後加粗並標示 ×3，供應平放的橘色五輻輪圈；第四卷灰色材料獨立供應輪緣與輪輻下方的灰色支撐格柵，支撐具有連接底座及橫向連結。"
   }
  }
 },
 "en": {
  "lang": "en",
  "heading": "Understand print modes",
  "selectMode": "Choose a print mode to view its description",
  "modes": {
   "dual": {
    "name": "Dual material",
    "title": "A / B dual material mode",
    "benefit": "Two filaments, configured separately",
    "body": "Print two colors, combine different or rigid and flexible materials, or use a separate filament for removable supports.",
    "limit": "",
    "alt": "Three dual material uses: removable supports, two-color parts and rigid-flexible combinations.",
    "applications": [
     {
      "id": "dual-support",
      "label": "Removable supports",
      "alt": "An orange drill half-shell is tilted with its cavity facing upward. Gray support grids with a connected base and cross-ties carry the overhangs beneath the curved housing, grip and foot."
     },
     {
      "id": "dual-color",
      "label": "Two-color part",
      "alt": "An orange outer ring and gray center join into a single two-color gear."
     },
     {
      "id": "dual-soft",
      "label": "Rigid + flexible",
      "alt": "A gray flexible grip wraps and joins the orange rigid frame as one complete handle."
     }
    ]
   },
   "cofeed": {
    "name": "Co-feed",
    "title": "Co-feed mode",
    "benefit": "High flow · Color gradients · Photo tiles",
    "body": "Use two spools of the same material: matching colors increase flow; different colors can change their blend ratio with print height or create photo tiles.",
    "limit": "",
    "alt": "Three co-feed uses: increased flow, color gradients and photo tiles.",
    "applications": [
     {
      "id": "cofeed",
      "label": "2× flow · 2× speed",
      "alt": "Two orange spools of the same material merge into a thicker orange line marked ×2 to print an orange part."
     },
     {
      "id": "cofeed-gradient",
      "label": "Color gradients",
      "alt": "Gray and orange spools of the same material merge. The borderless part transitions smoothly from gray at the bottom to orange at the top, with no internal dividing lines, showing a continuous change in blend ratio with height."
     },
     {
      "id": "photo",
      "label": "Photo tiles (in development)",
      "alt": "Photo tiles are in development. A photo becomes an upright printed tile, using color blending to reproduce the image."
     }
    ]
   },
   "single": {
    "name": "Single material",
    "title": "Single material mode",
    "benefit": "One material · One spool",
    "body": "For smaller prints, a single available spool, or jobs that do not need the extra flow of co-feed.",
    "limit": "",
    "alt": "One orange spool supplies an orange part made from one material."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "3× main-material flow · Separate removable supports",
    "body": "Three main filaments feed the part together. A fourth independently prints supports beneath the overhang.",
    "limit": "",
    "alt": "Three orange main feeds merge into a thicker orange line marked ×3 to supply a horizontal orange five-spoke wheel rim. A separate fourth gray feed supplies gray support grids beneath the rim and spokes, joined by a common base and transverse ties."
   }
  }
 },
 "de_DE": {
  "lang": "de",
  "heading": "Druckmodi kennenlernen",
  "selectMode": "Druckmodus auswählen, um die Beschreibung anzuzeigen",
  "modes": {
   "dual": {
    "name": "Zwei Materialien",
    "title": "A / B: Zwei Materialien",
    "benefit": "Zwei Filamente, getrennt eingestellt",
    "body": "Zweifarbig drucken, verschiedene oder harte und flexible Materialien kombinieren – oder ein Filament für entfernbare Stützen verwenden.",
    "limit": "",
    "alt": "Drei Anwendungen: entfernbare Stützen, zweifarbige Bauteile und die Kombination von hartem und flexiblem Material.",
    "applications": [
     {
      "id": "dual-support",
      "label": "Entfernbare Stützen",
      "alt": "Eine orangefarbene Gehäusehälfte einer Bohrmaschine liegt schräg mit der Öffnung nach oben. Graue Stützgitter mit verbundenem Sockel und Querverbindungen tragen die Überhänge unter Gehäuse, Griff und Fuß."
     },
     {
      "id": "dual-color",
      "label": "Zweifarbiges Bauteil",
      "alt": "Ein orangefarbener Außenring und eine graue Mitte bilden ein einziges zusammenhängendes Zahnrad."
     },
     {
      "id": "dual-soft",
      "label": "Hart + flexibel",
      "alt": "Ein flexibler grauer Griff umschließt den starren orangefarbenen Rahmen und ist mit ihm verbunden."
     }
    ]
   },
   "cofeed": {
    "name": "Gleichzeitige Zufuhr",
    "title": "Gleichzeitige Materialzufuhr",
    "benefit": "Hoher Durchfluss · Farbverläufe · Fotokacheln",
    "body": "Zwei Spulen desselben Materials: Gleiche Farben erhöhen den Durchfluss. Bei verschiedenen Farben kann das Mischverhältnis mit der Druckhöhe variieren oder für Fotokacheln genutzt werden.",
    "limit": "",
    "alt": "Drei Anwendungen der gleichzeitigen Zufuhr: mehr Durchfluss, Farbverläufe und Fotokacheln.",
    "applications": [
     {
      "id": "cofeed",
      "label": "Durchfluss ×2 · Tempo ×2",
      "alt": "Zwei orangefarbene Spulen desselben Materials vereinigen sich zu einer dickeren orangefarbenen Linie mit ×2 und drucken ein orangefarbenes Bauteil."
     },
     {
      "id": "cofeed-gradient",
      "label": "Farbverläufe",
      "alt": "Graue und orangefarbene Spulen desselben Materials werden zusammengeführt. Das Bauteil ohne Umrandung zeigt einen fließenden Verlauf von Grau unten zu Orange oben, ohne innere Trennlinien. Das Mischverhältnis ändert sich kontinuierlich mit der Höhe."
     },
     {
      "id": "photo",
      "label": "Fotokacheln (in Entwicklung)",
      "alt": "Fotokacheln sind in Entwicklung. Ein Foto wird als aufrecht gedruckte Kachel durch Farbmischung wiedergegeben."
     }
    ]
   },
   "single": {
    "name": "Ein Material",
    "title": "Drucken mit einem Material",
    "benefit": "Ein Material · Eine Spule",
    "body": "Für kleinere Druckmengen, nur eine verfügbare Spule oder Aufträge ohne zusätzlichen Durchfluss durch gleichzeitige Zufuhr.",
    "limit": "",
    "alt": "Eine orangefarbene Spule versorgt ein orangefarbenes Bauteil aus einem einzigen Material."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "Hauptmaterial-Durchfluss ×3 · Separate entfernbare Stützen",
    "body": "Drei Hauptfilamente versorgen gemeinsam das Bauteil. Ein viertes druckt separat die Stützen unter dem Überhang.",
    "limit": "",
    "alt": "Drei orangefarbene Hauptzuführungen vereinigen sich zu einer dickeren orangefarbenen Linie mit ×3 und versorgen eine waagerecht liegende orangefarbene Fünfspeichenfelge. Eine separate vierte graue Zuführung versorgt graue Stützgitter unter Felgenrand und Speichen, verbunden durch einen gemeinsamen Sockel und Querverbindungen."
   }
  }
 },
 "fr_FR": {
  "lang": "fr",
  "heading": "Comprendre les modes d’impression",
  "selectMode": "Choisir un mode d’impression pour afficher sa description",
  "modes": {
   "dual": {
    "name": "Deux matériaux",
    "title": "A / B : deux matériaux",
    "benefit": "Deux filaments, réglés séparément",
    "body": "Imprimez en deux couleurs, combinez des matériaux différents ou rigides et souples, ou réservez un filament aux supports amovibles.",
    "limit": "",
    "alt": "Trois usages : supports amovibles, pièce bicolore et combinaison rigide-souple.",
    "applications": [
     {
      "id": "dual-support",
      "label": "Supports amovibles",
      "alt": "Une demi-coque orange de perceuse est inclinée, sa cavité ouverte vers le haut. Des supports en treillis gris, reliés par une base commune et des traverses, soutiennent les surplombs sous le carter, la poignée et le pied."
     },
     {
      "id": "dual-color",
      "label": "Pièce bicolore",
      "alt": "La couronne orange et le centre gris sont unis en un seul engrenage bicolore."
     },
     {
      "id": "dual-soft",
      "label": "Rigide + souple",
      "alt": "La prise souple grise enveloppe le corps rigide orange et forme avec lui une poignée complète."
     }
    ]
   },
   "cofeed": {
    "name": "Co-alimentation",
    "title": "Co-alimentation",
    "benefit": "Haut débit · Dégradés · Plaques photo",
    "body": "Deux bobines du même matériau : une même couleur augmente le débit ; des couleurs différentes permettent de varier le mélange selon la hauteur ou de créer des plaques photo.",
    "limit": "",
    "alt": "Trois usages de la co-alimentation : débit accru, dégradés de couleur et plaques photo.",
    "applications": [
     {
      "id": "cofeed",
      "label": "Débit ×2 · Vitesse ×2",
      "alt": "Deux bobines orange du même matériau fusionnent en une ligne orange plus épaisse marquée ×2 pour imprimer une pièce orange."
     },
     {
      "id": "cofeed-gradient",
      "label": "Dégradés de couleur",
      "alt": "Des bobines grise et orange du même matériau fusionnent. La pièce sans contour passe progressivement du gris en bas à l’orange en haut, sans lignes de séparation internes, illustrant un mélange qui varie continuellement avec la hauteur."
     },
     {
      "id": "photo",
      "label": "Plaques photo (en développement)",
      "alt": "Les plaques photo sont en développement. Une photo devient une plaque imprimée à la verticale, reproduisant l’image par mélange des couleurs."
     }
    ]
   },
   "single": {
    "name": "Un matériau",
    "title": "Impression avec un matériau",
    "benefit": "Un matériau · Une bobine",
    "body": "Pour les petites impressions, une seule bobine disponible ou les travaux sans besoin du débit accru de la co-alimentation.",
    "limit": "",
    "alt": "Une bobine orange alimente une pièce orange faite d’un seul matériau."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "Débit du matériau principal ×3 · Supports amovibles séparés",
    "body": "Trois filaments principaux alimentent la pièce ensemble. Un quatrième imprime séparément les supports sous le surplomb.",
    "limit": "",
    "alt": "Trois alimentations principales orange fusionnent en une ligne orange plus épaisse marquée ×3 pour alimenter une jante horizontale orange à cinq branches. Une quatrième alimentation grise indépendante fournit les supports en treillis gris sous le bord et les branches, reliés par une base commune et des traverses."
   }
  }
 }
};

var PingModeIds = ['dual', 'cofeed', 'single', 'three'];   /* Eric 0908：ABS 關門頁籤拿掉（它是 FD300 關門的範圔限制，不是列印模式） */
var PingModeArt = {
  'dual-support': '../ping-modes/dual-support.png',
  'dual-color': '../ping-modes/dual-color.png',
  'dual-soft': '../ping-modes/dual-soft.png',
  'cofeed': '../ping-modes/cofeed.png',
  'cofeed-gradient': '../ping-modes/cofeed-gradient.png',
  'photo': '../ping-modes/photo.png',
  'single': '../ping-modes/single.png',
  'three': '../ping-modes/three.png'
};
var PingModeState = { mode: 'dual' };

function PingModeLang() {
  var l = null;
  try { if (typeof GetQueryString === 'function') l = GetQueryString('lang'); } catch (e) { l = null; }
  if (!l) { try { l = localStorage.getItem('BambuWebLang'); } catch (e) { l = null; } }
  if (l === 'zh_CN') l = 'zh_TW';            // 與 TranslatePage() 同一條規則：PING 偏繁中
  if (!l || !PingModeCopy.hasOwnProperty(l)) l = 'en';
  return l;
}

/* 只給 PING 廠牌區塊；其他廠牌回空字串（本頁目前只有 PING）。 */
function PingModeHelpHtml(vendor) {
  if (vendor !== 'PING') return '';
  /* Eric 2026-09-08：「認識列印模式」那行不要（頁籤本身已說明用途），不產 heading 節點。 */
  return '<section id="PingModeHelp" class="PingModeHelp">' +
    '<div class="pmh-modes" role="tablist"></div>' +
    '<div class="pmh-detail" role="region" aria-live="polite" aria-atomic="true">' +
      '<div class="pmh-copy">' +
        '<h3 class="pmh-title" id="pmh-title"></h3>' +
        '<p class="pmh-benefit"></p>' +
        '<p class="pmh-body"></p>' +
        '<p class="pmh-material-note" hidden></p>' +
        '<p class="pmh-limit" hidden></p>' +
      '</div>' +
      '<div class="pmh-cases"></div>' +
      '<img class="pmh-single-art" alt="" hidden>' +
    '</div>' +
  '</section>';
}

function PingModeHelpInit() {
  var root = document.getElementById('PingModeHelp');
  if (!root) return;
  var tabs = root.querySelector('.pmh-modes');
  if (!tabs.children.length) {
    PingModeIds.forEach(function (id) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'pmh-mode'; b.setAttribute('role', 'tab');
      b.dataset.mode = id; b.setAttribute('aria-selected', 'false');
      b.addEventListener('click', function () { PingModeState.mode = id; PingModeHelpRender(); });
      /* 鍵盤：左右鍵在頁籤間移動（tablist 慣例），Enter／Space 是 button 原生。 */
      b.addEventListener('keydown', function (ev) {
        if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
        var i = PingModeIds.indexOf(PingModeState.mode);
        i = (i + (ev.key === 'ArrowRight' ? 1 : PingModeIds.length - 1)) % PingModeIds.length;
        PingModeState.mode = PingModeIds[i]; PingModeHelpRender();
        var nb = tabs.querySelector('.pmh-mode[data-mode="' + PingModeIds[i] + '"]'); if (nb) nb.focus();
        ev.preventDefault();
      });
      tabs.appendChild(b);
    });
  }
  PingModeHelpRender();
}

function PingModeHelpRender() {
  var root = document.getElementById('PingModeHelp');
  if (!root) return;
  var lang = PingModeLang();
  var sel = PingModeCopy[lang] || PingModeCopy.en;
  var base = PingModeCopy.en.modes[PingModeState.mode] || {};
  var mode = {}; var k;
  for (k in base) mode[k] = base[k];
  var over = (sel.modes || {})[PingModeState.mode] || {};
  for (k in over) mode[k] = over[k];

  root.lang = sel.lang || 'en';
  root.setAttribute('aria-label', sel.heading);   /* heading 只留給輔助技術，不畫在畫面上（Eric 0908） */
  var tabs = root.querySelector('.pmh-modes');
  tabs.setAttribute('aria-label', sel.selectMode);
  tabs.querySelectorAll('.pmh-mode').forEach(function (b) {
    var id = b.dataset.mode;
    var name = ((sel.modes[id] || {}).name) || PingModeCopy.en.modes[id].name;
    b.textContent = name; b.setAttribute('aria-label', name);
    var on = (id === PingModeState.mode);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
    b.tabIndex = on ? 0 : -1;
  });

  var detail = root.querySelector('.pmh-detail');
  detail.dataset.mode = PingModeState.mode;
  root.querySelector('.pmh-title').textContent = mode.title || '';
  root.querySelector('.pmh-benefit').textContent = mode.benefit || '';
  root.querySelector('.pmh-body').textContent = mode.body || '';
  var note = root.querySelector('.pmh-material-note');
  note.textContent = mode.materialNote || ''; note.hidden = !mode.materialNote;
  var limit = root.querySelector('.pmh-limit');
  limit.textContent = mode.limit || ''; limit.hidden = !mode.limit;

  var apps = Array.isArray(mode.applications) ? mode.applications : [];
  var cases = root.querySelector('.pmh-cases');
  var single = root.querySelector('.pmh-single-art');
  detail.dataset.layout = apps.length ? 'applications' : 'single';
  cases.hidden = !apps.length; single.hidden = !!apps.length;
  if (apps.length) {
    cases.style.setProperty('--pmh-case-count', String(apps.length));
    /* 圖組依模式重建（雙料 3／同進 3／ABS 2），用 textContent 填文案、不吃 HTML。 */
    while (cases.firstChild) cases.removeChild(cases.firstChild);
    apps.forEach(function (a) {
      var fig = document.createElement('figure'); fig.className = 'pmh-case'; fig.dataset.case = a.id;
      var img = document.createElement('img'); img.src = PingModeArt[a.id] || ''; img.alt = a.alt || ''; img.width = 320; img.height = 320;
      var cap = document.createElement('figcaption'); cap.textContent = a.label || '';
      fig.appendChild(img); fig.appendChild(cap); cases.appendChild(fig);
    });
  } else {
    single.src = PingModeArt[PingModeState.mode] || '';
    single.alt = mode.alt || '';
  }
}
