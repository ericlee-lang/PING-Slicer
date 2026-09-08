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
      "alt": "灰色電鑽半邊外殼斜放，開口朝上；橘色支撐格柵以連接底座與橫向連結托住弧形外殼、握把及底座下方的懸空處。"
     },
     {
      "id": "dual-color",
      "label": "雙色列印",
      "alt": "灰色外環與橘色中心直接相接，構成同一件雙色齒輪。"
     },
     {
      "id": "dual-soft",
      "label": "軟硬結合",
      "alt": "橘色軟質握把包覆並接合灰色硬質本體，形成一件完整產品。"
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
      "alt": "兩卷同色材料匯流後主線加粗並標示 ×2，列印單色零件。"
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
   "closed": {
    "name": "ABS 關門",
    "title": "ABS 關門模式",
    "benefit": "雙料延伸・噴嘴 245°C",
    "body": "沿用雙料設定並提高溫度，關門保溫有助減少翹曲。",
    "materialNote": "暫無軟硬結合：兩進一出需共用 245°C，目前無適配此配置的軟料。",
    "limit": "FD300 關門：Ø 200 mm；Pro 外罩機型：開關門不影響列印範圍。",
    "alt": "ABS 關門沿用雙料的易拆支撐與雙色列印用途。",
    "applications": [
     {
      "id": "dual-support",
      "label": "ABS 主體＋易拆支撐",
      "alt": "灰色 ABS 電鑽半邊外殼依參考角度斜放；橘色支撐格柵以連接底座與橫向連結，從下方托住外殼的懸空處。"
     },
     {
      "id": "dual-color",
      "label": "ABS 雙色列印",
      "alt": "灰色外環與橘色中心直接相接，構成同一件 ABS 雙色齒輪。"
     }
    ]
   },
   "single": {
    "name": "單料頭",
    "title": "單料頭模式",
    "benefit": "一種材料・一卷即可",
    "body": "適合列印量較少、只有一卷材料，或不需同進額外流量的情境。",
    "limit": "",
    "alt": "一卷材料供料，列印單一材料的零件。"
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "主材流量 ×3・獨立易拆支撐",
    "body": "三支主材合流列印主體，第四支材料獨立列印懸空面下方的支撐。",
    "limit": "",
    "alt": "三卷炭黑主材線合流後加粗並標示 ×3，供應平放的五輻輪圈；第四卷橘色材料獨立供應輪緣與輪輻下方的支撐格柵，支撐具有連接底座及橫向連結。"
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
      "alt": "A gray drill half-shell is tilted with its cavity facing upward. Orange support grids with a connected base and cross-ties carry the overhangs beneath the curved housing, grip and foot."
     },
     {
      "id": "dual-color",
      "label": "Two-color part",
      "alt": "A gray outer ring and orange center join into a single two-color gear."
     },
     {
      "id": "dual-soft",
      "label": "Rigid + flexible",
      "alt": "An orange flexible grip wraps and joins the gray rigid frame as one complete handle."
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
      "alt": "Two matching-color feeds merge into a thicker line marked ×2 to print a single-color part."
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
   "closed": {
    "name": "ABS / Enclosed",
    "title": "ABS enclosed mode",
    "benefit": "Dual material extension · Nozzle 245°C",
    "body": "Use the dual material settings at a higher temperature. Closing the door retains heat and helps reduce warping.",
    "materialNote": "No rigid + flexible option: this two-in/one-out setup shares 245°C, and no compatible flexible filament is currently available for it.",
    "limit": "FD300, door closed: Ø 200 mm. Enclosed Pro models: opening or closing the door does not change the print area.",
    "alt": "ABS enclosed mode uses the removable-support and two-color applications of dual material mode.",
    "applications": [
     {
      "id": "dual-support",
      "label": "ABS + removable supports",
      "alt": "A gray ABS drill half-shell is tilted as in the reference. Orange support grids with a connected base and cross-ties carry its overhangs from below."
     },
     {
      "id": "dual-color",
      "label": "Two-color ABS",
      "alt": "The gray outer ring and orange center form one continuous two-color ABS gear."
     }
    ]
   },
   "single": {
    "name": "Single material",
    "title": "Single material mode",
    "benefit": "One material · One spool",
    "body": "For smaller prints, a single available spool, or jobs that do not need the extra flow of co-feed.",
    "limit": "",
    "alt": "One spool supplies a part made from one material."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "3× main-material flow · Separate removable supports",
    "body": "Three main filaments feed the part together. A fourth independently prints supports beneath the overhang.",
    "limit": "",
    "alt": "Three charcoal main feeds merge into a thicker line marked ×3 to supply a horizontal five-spoke wheel rim. A separate fourth orange feed supplies support grids beneath the rim and spokes, joined by a common base and transverse ties."
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
      "alt": "Eine graue Gehäusehälfte einer Bohrmaschine liegt schräg mit der Öffnung nach oben. Orangefarbene Stützgitter mit verbundenem Sockel und Querverbindungen tragen die Überhänge unter Gehäuse, Griff und Fuß."
     },
     {
      "id": "dual-color",
      "label": "Zweifarbiges Bauteil",
      "alt": "Grauer Außenring und orange Mitte bilden ein einziges zusammenhängendes Zahnrad."
     },
     {
      "id": "dual-soft",
      "label": "Hart + flexibel",
      "alt": "Ein flexibler orangefarbener Griff umschließt den starren grauen Rahmen und ist mit ihm verbunden."
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
      "alt": "Zwei gleichfarbige Zuführungen vereinigen sich zu einer dickeren Linie mit ×2 und drucken ein einfarbiges Bauteil."
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
   "closed": {
    "name": "ABS / Geschlossen",
    "title": "ABS bei geschlossener Tür",
    "benefit": "Erweiterung des Zweimaterialmodus · Düse 245°C",
    "body": "Die Einstellungen des Zweimaterialmodus werden mit höherer Temperatur genutzt. Die geschlossene Tür hält Wärme und verringert Verzug.",
    "materialNote": "Keine Hart-Flexibel-Kombination: Beide Zuführungen dieses 2-in-1-Ausgang-Systems nutzen 245°C. Dafür ist derzeit kein passendes flexibles Filament verfügbar.",
    "limit": "FD300 mit geschlossener Tür: Ø 200 mm. Pro-Modelle mit Gehäuse: Der Druckbereich bleibt beim Öffnen und Schließen unverändert.",
    "alt": "Der ABS-Modus übernimmt entfernbare Stützen und zweifarbige Bauteile aus dem Zweimaterialmodus.",
    "applications": [
     {
      "id": "dual-support",
      "label": "ABS + entfernbare Stützen",
      "alt": "Eine graue ABS-Gehäusehälfte einer Bohrmaschine ist wie in der Vorlage geneigt. Orangefarbene Stützgitter mit verbundenem Sockel und Querverbindungen tragen ihre Überhänge von unten."
     },
     {
      "id": "dual-color",
      "label": "Zweifarbiges ABS",
      "alt": "Grauer Außenring und orange Mitte bilden ein einziges zusammenhängendes ABS-Zahnrad."
     }
    ]
   },
   "single": {
    "name": "Ein Material",
    "title": "Drucken mit einem Material",
    "benefit": "Ein Material · Eine Spule",
    "body": "Für kleinere Druckmengen, nur eine verfügbare Spule oder Aufträge ohne zusätzlichen Durchfluss durch gleichzeitige Zufuhr.",
    "limit": "",
    "alt": "Eine Spule versorgt ein Bauteil aus einem einzigen Material."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "Hauptmaterial-Durchfluss ×3 · Separate entfernbare Stützen",
    "body": "Drei Hauptfilamente versorgen gemeinsam das Bauteil. Ein viertes druckt separat die Stützen unter dem Überhang.",
    "limit": "",
    "alt": "Drei anthrazitfarbene Hauptzuführungen vereinigen sich zu einer dickeren Linie mit ×3 und versorgen eine waagerecht liegende Fünfspeichenfelge. Eine separate vierte orangefarbene Zuführung versorgt Stützgitter unter Felgenrand und Speichen, verbunden durch einen gemeinsamen Sockel und Querverbindungen."
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
      "alt": "Une demi-coque grise de perceuse est inclinée, sa cavité ouverte vers le haut. Des supports en treillis orange, reliés par une base commune et des traverses, soutiennent les surplombs sous le carter, la poignée et le pied."
     },
     {
      "id": "dual-color",
      "label": "Pièce bicolore",
      "alt": "La couronne grise et le centre orange sont unis en un seul engrenage bicolore."
     },
     {
      "id": "dual-soft",
      "label": "Rigide + souple",
      "alt": "La prise souple orange enveloppe le corps rigide gris et forme avec lui une poignée complète."
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
      "alt": "Deux alimentations de même couleur fusionnent en une ligne plus épaisse marquée ×2 pour imprimer une pièce unicolore."
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
   "closed": {
    "name": "ABS / Fermé",
    "title": "ABS, porte fermée",
    "benefit": "Extension du mode à deux matériaux · Buse 245°C",
    "body": "Les réglages du mode à deux matériaux sont repris à une température plus élevée. Fermer la porte conserve la chaleur et réduit le gauchissement.",
    "materialNote": "Pas de combinaison rigide + souple : les deux entrées partagent une sortie à 245°C, sans filament souple actuellement compatible avec cette configuration.",
    "limit": "FD300, porte fermée : Ø 200 mm. Modèles Pro avec enceinte : ouvrir ou fermer la porte ne modifie pas la zone d’impression.",
    "alt": "Le mode ABS reprend les supports amovibles et l’impression bicolore du mode à deux matériaux.",
    "applications": [
     {
      "id": "dual-support",
      "label": "ABS + supports amovibles",
      "alt": "Une demi-coque de perceuse en ABS gris est inclinée comme sur la référence. Des supports en treillis orange, reliés par une base commune et des traverses, soutiennent ses surplombs par-dessous."
     },
     {
      "id": "dual-color",
      "label": "ABS bicolore",
      "alt": "La couronne grise et le centre orange constituent un seul engrenage ABS bicolore."
     }
    ]
   },
   "single": {
    "name": "Un matériau",
    "title": "Impression avec un matériau",
    "benefit": "Un matériau · Une bobine",
    "body": "Pour les petites impressions, une seule bobine disponible ou les travaux sans besoin du débit accru de la co-alimentation.",
    "limit": "",
    "alt": "Une bobine alimente une pièce faite d’un seul matériau."
   },
   "three": {
    "name": "3 in 1",
    "title": "3 in 1",
    "benefit": "Débit du matériau principal ×3 · Supports amovibles séparés",
    "body": "Trois filaments principaux alimentent la pièce ensemble. Un quatrième imprime séparément les supports sous le surplomb.",
    "limit": "",
    "alt": "Trois alimentations principales anthracite fusionnent en une ligne plus épaisse marquée ×3 pour alimenter une jante horizontale à cinq branches. Une quatrième alimentation orange indépendante fournit les supports en treillis sous le bord et les branches, reliés par une base commune et des traverses."
   }
  }
 }
};

var PingModeIds = ['dual', 'cofeed', 'closed', 'single', 'three'];
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
  return '<section id="PingModeHelp" class="PingModeHelp">' +
    '<p class="pmh-heading"></p>' +
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
  root.setAttribute('aria-label', sel.heading);
  root.querySelector('.pmh-heading').textContent = sel.heading;
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
