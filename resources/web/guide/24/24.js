function OnInit()
{
	//let strInput=JSON.stringify(cData);
	//HandleStudio(strInput);
	
	TranslatePage();
	
	RequestProfile();
}



function RequestProfile()
{
	var tSend={};
	tSend['sequence_id']=Math.round(new Date() / 1000);
	tSend['command']="request_userguide_profile";
	
	SendWXMessage( JSON.stringify(tSend) );
}

function HandleStudio( pVal )
{
//	alert(strInput);
//	alert(JSON.stringify(strInput));
//	
//	let pVal=IsJson(strInput);
//	if(pVal==null)
//	{
//		alert("Msg Format Error is not Json");
//		return;
//	}
	
	let strCmd=pVal['command'];
	//alert(strCmd);
	
	if(strCmd=='response_userguide_profile')
	{
		HandleModelList(pVal['response']);
	}
}

function ShowPrinterThumb(pItem, strImg)
{
	$(pItem).attr('src',strImg);
	$(pItem).attr('onerror',null);
}

// PING V3.6：同一個印表機選擇頁分 Fast／Classic，避免再增加精靈步驟。
const PingClassicModels = new Set([
	'EDU 200', 'PING 200', 'PING 270', 'PING 300+',
	'DUAL 300', 'DUAL 450', 'DUAL 600', 'DUAL 800'
]);
let PingProductLine = 'fast';
let PingSearchKeyword = '';

// PING: 機型名去掉變體字尾＝「系列／基本機型名」。分組與產品線分類共用同一條規則。
// 🔴 **不可**把「同進照片磚」加進這個清單（2026-08-13 實測後撤回）：加了之後照片磚機會併進
//    母系列（FD300…），而系列卡的產品線取「該系列第一台」的分類 ⇒ 照片磚被歸到 Fast 分頁，
//    違反 Eric 2026-07-19 裁「照片磚設為一類」。照片磚維持自成一個系列。
const PING_VARIANT_SUFFIX = /\s*(單料頭|單噴頭|同進|3in1|關門)$/;
function PingBaseModel(model) { return model.replace(PING_VARIANT_SUFFIX, ''); }

// PING 2026-08-13（Eric 裁丙案）：本體變體（無後綴）的顯示名＝該機的**料數**。
// 值域由實查各系列本體的 default_filament_profile 槽數定（2026-08-13）：
//   FF600／FF800 ＝ 4 槽 ⇒ 四料｜FD 系與 DUAL 系 ＝ 2 槽 ⇒ 雙料｜其餘（FP300／EDU 200／
//   PING 200・270・300+／DL1016）＝ 1 槽 ⇒ 單料。
// ⚠ Eric 原話是「本體改成雙料」，但那只對 2 槽機成立；FF 系是四料機，一律寫雙料會標錯，
//   故按槽數推導。要改成一律「雙料」需 Eric 另裁。
function PingBaseLabel(series) {
	// 照片磚機是 64 個虛擬料槽（照片磚工作室用），不套「幾料」的說法
	if (series.indexOf('照片磚') != -1) return '照片磚';
	if (/^FF/.test(series))        return '四料';
	if (/^(FD|DUAL)/.test(series)) return '雙料';
	return '單料';
}

// 變體顯示名＝機型名去掉系列名後剩下的後綴；本體（沒有後綴）用料數當名字。
// 例：FD300 → 雙料｜FD300 同進 → 同進｜FF800 3in1 → 3in1｜FD300 同進照片磚 → 同進照片磚
function PingVariantLabel(model, series) {
	let s = model.slice(series.length).trim();
	return s === '' ? PingBaseLabel(series) : s;
}

function ProductLineOf(vendor, model) {
	// 照片磚機獨立一類（Eric 2026-07-19 定：照片磚設為一類、含不同範圍的機器）
	if (vendor == 'PING' && model.indexOf('照片磚') != -1) return 'phototile';
	// 🔴 PING 2026-08-13 修：白名單收的是「基本機型名」，必須先去掉變體字尾再比對。
	//    舊版拿**完整機型名**去 has() ⇒「DUAL 300 同進」「DUAL 300 單料頭」比不到 ⇒ 落到 fast，
	//    而本體「DUAL 300」在 classic ⇒ 同型號家族被拆到兩個分頁（違 LAY-11，使用者在
	//    Classic 分頁找不到自己機器的同進版）。四組 DUAL 全中。
	return vendor == 'PING' && PingClassicModels.has(PingBaseModel(model)) ? 'classic' : 'fast';
}

function ProductLineTabs(vendor) {
	if (vendor != 'PING') return '';
	return '<div class="ProductLineTabs" role="tablist" aria-label="PING product line">' +
		'<button type="button" class="ProductLineTab" data-line="fast" onclick="SetPingProductLine(\'fast\')">Fast</button>' +
		'<button type="button" class="ProductLineTab" data-line="classic" onclick="SetPingProductLine(\'classic\')">Classic</button>' +
		'<button type="button" class="ProductLineTab" data-line="phototile" onclick="SetPingProductLine(\'phototile\')">照片磚</button>' +
		'</div>';
}

function SetPingProductLine(line) {
	PingProductLine = line;
	ApplyPingProductLine();
}

function ApplyPingProductLine() {
	let searching = PingSearchKeyword.trim() != '';
	document.querySelectorAll(".OneVendorBlock[vendor='PING'] .PrinterBlock[data-product-line]").forEach(function(card) {
		card.style.display = (searching || card.dataset.productLine == PingProductLine) ? '' : 'none';
	});
	document.querySelectorAll(".OneVendorBlock[vendor='PING'] .ProductLineTab").forEach(function(tab) {
		let active = tab.dataset.line == PingProductLine;
		tab.classList.toggle('active', active);
		tab.setAttribute('aria-selected', active ? 'true' : 'false');
	});
}

function HandleModelList( pVal )
{
	if( !pVal.hasOwnProperty("model") )
		return;

	pModel=pVal['model'];
	PingSearchKeyword='';
	
	let nTotal=pModel.length;
	let ModelHtml={};
	for(let n=0;n<nTotal;n++)
	{
		let OneModel=pModel[n];
		
		let strVendor=OneModel['vendor'];
		
		//Add Vendor Html Node
		if($(".OneVendorBlock[vendor='"+strVendor+"']").length==0)
		{
			let sVV=strVendor;
			if( sVV=="BBL" )
				sVV="Bambu Lab";			
			if( sVV=="Custom")
				sVV="Custom Printer";
			if( sVV=="Other")
				sVV="Orca colosseum";

			let HtmlNewVendor='<div class="OneVendorBlock" Vendor="'+strVendor+'">'+
'<div class="BlockBanner">'+
'	<div class="BannerBtns">'+
'		<div class="SmallBtn_Green trans" tid="t11" onClick="SelectPrinterAll('+"\'"+strVendor+"\'"+')">all</div>'+
'		<div class="SmallBtn trans" tid="t12" onClick="SelectPrinterNone('+"\'"+strVendor+"\'"+')">none</div>'+
'	</div>'+
'	<a>'+sVV+'</a>'+
'</div>'+
ProductLineTabs(strVendor)+
'<div class="PrinterArea">	'+
'</div>'+
'</div>';
			
			$('#Content').append(HtmlNewVendor);
		}
		
		let ModelName=OneModel['model'];

		//Collect Html Node Nozzel Html
		//PING: 依「家族」分組(機型名去掉模式字尾 單料頭/同進)，每家族一列(基本/單料頭/同進 三卡)
		let strSeries=PingBaseModel(ModelName);
		if( !ModelHtml.hasOwnProperty(strVendor))
			ModelHtml[strVendor]={};
		if( !ModelHtml[strVendor].hasOwnProperty(strSeries))
			ModelHtml[strVendor][strSeries]={cover:OneModel['cover'],
			                                 line:ProductLineOf(strVendor, ModelName), rows:''};

		// PING 2026-08-13（Eric 裁丙案）：一個系列一張卡，變體在圖下方**垂直勾選**。
		// 卡片形狀與舊版相同（圖＋底下一串勾選框），只是勾選框的內容從「口徑」換成「變體」
		// ⇒ 使用者不必重新認識版面（LAY-12 結構一致性），而且一系列一張卡之後卡片不必各佔一列。
		// 口徑不在此選（機型啟用＝該機型全部口徑可用），留到切片時在主畫面決定。
		ModelHtml[strVendor][strSeries].rows +=
'<div class="VarRow" data-vendor="'+strVendor+'" data-model="'+OneModel['model']+
'" data-nozzles="'+OneModel['nozzle_diameter']+'" onclick="ChooseModel(this)">'+
'<span class="PSel"></span><span class="VarName">'+PingVariantLabel(OneModel['model'], strSeries)+'</span></div>';
	}

	//Append —— PING: 一個系列一張卡。**沿用 .PrinterBlock class**，讓產品線過濾
	//（ApplyPingProductLine）與「跳過隱藏卡」邏輯不必改。
	for( let key in ModelHtml )
	{
		let pArea=$(".OneVendorBlock[vendor='"+key+"'] .PrinterArea");
		for( let series in ModelHtml[key] )
		{
			let g=ModelHtml[key][series];
			pArea.append('<div class="PrinterBlock" data-product-line="'+g.line+'" data-series="'+series+'">'+
'	<div class="PImg"><img src="'+g.cover+'"  /></div>'+
'	<div class="SeriesName">'+series+'</div>'+ g.rows +'</div>');
		}
	}
	
	
	//Update Checkbox —— PING 2026-08-13：改機型層級（任一口徑被記錄＝整台已選）
	for(let m=0;m<nTotal;m++)
	{
		let OneModel=pModel[m];

		let SelectList=OneModel['nozzle_selected'];
		if(SelectList!='')
		{
			SelectList=SelectList.split(';');
			for(let a=0;a<SelectList.length;a++)
			{
				if(SelectList[a]=='') continue;
				SetModelSelect(OneModel['vendor'], OneModel['model'], SelectList[a], true);
			}
		}
	}
	SyncAllCards();

	// let AlreadySelect=$("input:checked");
	// let nSelect=AlreadySelect.length;
	// if(nSelect==0)
	// {
	// 	$("input[nozzel='0.4'][vendor='Custom']").prop("checked", true);
	// }
	
	ApplyPingProductLine();
	TranslatePage();
}

function CheckBoxOnclick(obj) {

	let strModel = obj.getAttribute("model");

	let strVendor = obj.getAttribute("vendor");
	let strNozzel = obj.getAttribute("nozzel");

	SetModelSelect(strVendor, strModel, strNozzel, obj.checked);

}

function SetModelSelect(vendor, model, nozzel, checked) {
	if (!ModelNozzleSelected.hasOwnProperty(vendor) && !checked) {
		return;
	}

	if (!ModelNozzleSelected.hasOwnProperty(vendor) && checked) {
		ModelNozzleSelected[vendor] = {};
	}

	let oVendor = ModelNozzleSelected[vendor];
	if (!oVendor.hasOwnProperty(model)) {
		oVendor[model] = {};
	}

	let oModel = oVendor[model];
	if (oModel.hasOwnProperty(nozzel) || checked) {
		oVendor[model][nozzel] = checked;
	}
}

function GetModelSelect(vendor, model, nozzel) {
	if (!ModelNozzleSelected.hasOwnProperty(vendor)) {
		return false;
	}

	let oVendor = ModelNozzleSelected[vendor];
	if (!oVendor.hasOwnProperty(model)) {
		return false;
	}

	let oModel = oVendor[model];
	if (!oModel.hasOwnProperty(nozzel)) {
		return false;
	}

	return oVendor[model][nozzel];
}

// ── PING 2026-08-13（Eric 裁「拿掉口徑勾選、只勾機型」）─────────────────────────
// 動線改成：整張卡片可點＝選這台機器，該機型**全部口徑**一起啟用；
// 口徑留到切片時在主畫面左上角的下拉決定（裝機當下使用者還不知道下一個檔要用哪個噴嘴）。
// ⓘ 底層儲存結構 ModelNozzleSelected[vendor][model][nozzle] **不變**——只是改由卡片一次寫入
//    整組口徑，所以 OnExitFilter() 的序列化、C++ 端的收訊與 AppConfig 格式全都不必動。
// ⚠ 必須寫入完整口徑清單（不可留空集合）：AppConfig::save() 對 variant 集合為空的 model
//    直接 `continue` 不寫出 ⇒ 空集合會讓整台機器從設定檔消失。
// row ＝ 一個 .VarRow（一台機器＝系列裡的一個變體）
function SetCardSelected(row, on) {
	let vendor  = row.getAttribute('data-vendor');
	let model   = row.getAttribute('data-model');
	let nozzles = (row.getAttribute('data-nozzles') || '').split(';');
	for (let i = 0; i < nozzles.length; i++) {
		if (nozzles[i] == '') continue;
		SetModelSelect(vendor, model, nozzles[i], on);
	}
	row.classList.toggle('Selected', on);
}

function ChooseModel(row) {
	SetCardSelected(row, !row.classList.contains('Selected'));
}

// 依 ModelNozzleSelected 回填變體列外觀：**任一口徑被記錄＝該台視為已選**
// （相容舊 conf：既有使用者只勾過 0.6 的機器，改版後仍顯示為已選。）
function SyncCardSelected(row) {
	let vendor  = row.getAttribute('data-vendor');
	let model   = row.getAttribute('data-model');
	let nozzles = (row.getAttribute('data-nozzles') || '').split(';');
	let on = false;
	for (let i = 0; i < nozzles.length; i++) {
		if (nozzles[i] != '' && GetModelSelect(vendor, model, nozzles[i])) { on = true; break; }
	}
	row.classList.toggle('Selected', on);
}

function SyncAllCards() {
	document.querySelectorAll('.VarRow[data-model]').forEach(SyncCardSelected);
}
// ────────────────────────────────────────────────────────────────────────────

function FilterModelList(keyword) {
	PingSearchKeyword = keyword;

	// PING 2026-08-13：不必再從 DOM 回收勾選狀態——ChooseModel/SetCardSelected 在點擊當下
	// 就寫進 ModelNozzleSelected，搜尋重建 DOM 不會遺失（重建後靠 SyncAllCards 回填外觀）。

	let nTotal = pModel.length;
	let ModelHtml = {};

	$('#Content').empty();
	for (let n = 0; n < nTotal; n++) {
		let OneModel = pModel[n];

		let strVendor = OneModel['vendor'];
		let ModelName = OneModel['model'];
		if (ModelName.toLowerCase().indexOf(keyword.toLowerCase()) == -1)
			continue;

		//Add Vendor Html Node
		if ($(".OneVendorBlock[vendor='" + strVendor + "']").length == 0) {
			let sVV = strVendor;
			if (sVV == "BBL")
				sVV = "Bambu Lab";
			if (sVV == "Custom")
				sVV = "Custom Printer";
			if (sVV == "Other")
				sVV = "Orca colosseum";

			let HtmlNewVendor = '<div class="OneVendorBlock" Vendor="' + strVendor + '">' +
				'<div class="BlockBanner">' +
				'	<div class="BannerBtns">' +
				'		<div class="SmallBtn_Green trans" tid="t11" onClick="SelectPrinterAll(' + "\'" + strVendor + "\'" + ')">all</div>' +
				'		<div class="SmallBtn trans" tid="t12" onClick="SelectPrinterNone(' + "\'" + strVendor + "\'" + ')">none</div>' +
				'	</div>' +
				'	<a>' + sVV + '</a>' +
				'</div>' +
				ProductLineTabs(strVendor) +
				'<div class="PrinterArea">	' +
				'</div>' +
				'</div>';

			$('#Content').append(HtmlNewVendor);
		}

		//Collect Html Node Nozzel Html
		//PING: 同 HandleModelList，依家族分組(去模式字尾)
		let strSeries = PingBaseModel(ModelName);
		if (!ModelHtml.hasOwnProperty(strVendor))
			ModelHtml[strVendor] = {};
		if (!ModelHtml[strVendor].hasOwnProperty(strSeries))
			ModelHtml[strVendor][strSeries] = {cover: OneModel['cover'],
			                                   line: ProductLineOf(strVendor, ModelName), rows: ''};

		// PING 2026-08-13：同 HandleModelList——一系列一張卡、變體垂直勾選
		ModelHtml[strVendor][strSeries].rows +=
			'<div class="VarRow" data-vendor="' + strVendor + '" data-model="' + OneModel['model'] +
			'" data-nozzles="' + OneModel['nozzle_diameter'] + '" onclick="ChooseModel(this)">' +
			'<span class="PSel"></span><span class="VarName">' + PingVariantLabel(OneModel['model'], strSeries) + '</span></div>';
	}

	//Append —— PING: 一系列一張卡（沿用 .PrinterBlock class 讓產品線過濾不必改）
	for (let key in ModelHtml) {
		let obj = $(".OneVendorBlock[vendor='" + key + "'] .PrinterArea");
		obj.empty();
		for (let series in ModelHtml[key]) {
			let g = ModelHtml[key][series];
			obj.append('<div class="PrinterBlock" data-product-line="' + g.line + '" data-series="' + series + '">' +
				'	<div class="PImg"><img src="' + g.cover + '"  /></div>' +
				'	<div class="SeriesName">' + series + '</div>' + g.rows + '</div>');
		}
	}


	//Update Checkbox —— PING 2026-08-13：重建 DOM 後依 ModelNozzleSelected 回填卡片外觀
	SyncAllCards();

	// let AlreadySelect=$("input:checked");
	// let nSelect=AlreadySelect.length;
	// if(nSelect==0)
	// {
	// 	$("input[nozzel='0.4'][vendor='Custom']").prop("checked", true);
	// }

	ApplyPingProductLine();
	TranslatePage();
}

// PING: 改用 native querySelectorAll + 直接設值，移除 jQuery 逐元素 $(this) 包裝開銷（加速全選/全部清空）
// PING 2026-08-13：改走變體列（口徑 checkbox 已移除）；隱藏的系列卡（產品線分頁/搜尋過濾掉的）一律跳過。
function SetAllCards(sVendor, on) {
	let rows = document.querySelectorAll(".VarRow[data-vendor='" + sVendor + "']");
	for (let i = 0; i < rows.length; i++) {
		let card = rows[i].closest('.PrinterBlock');
		if (sVendor == 'PING' && card && card.style.display == 'none') continue;
		SetCardSelected(rows[i], on);
	}
}

function SelectPrinterAll(sVendor)  { SetAllCards(sVendor, true);  }
function SelectPrinterNone(sVendor) { SetAllCards(sVendor, false); }

function OnExitFilter() {

	let nTotal = 0;
	let ModelAll = {};
	for (vendor in ModelNozzleSelected) {
		for (model in ModelNozzleSelected[vendor]) {
			for (nozzel in ModelNozzleSelected[vendor][model]) {
				if (!ModelNozzleSelected[vendor][model][nozzel])
					continue;

				if (!ModelAll.hasOwnProperty(model)) {
					//alert("ADD: "+strModel);

					ModelAll[model] = {};

					ModelAll[model]["model"] = model;
					ModelAll[model]["nozzle_diameter"] = '';
					ModelAll[model]["vendor"] = vendor;
				}

				ModelAll[model]["nozzle_diameter"] += ModelAll[model]["nozzle_diameter"] == '' ? nozzel : ';' + nozzel;

				nTotal++;
			}

		}
	}

	var tSend = {};
	tSend['sequence_id'] = Math.round(new Date() / 1000);
	tSend['command'] = "save_userguide_models";
	tSend['data'] = ModelAll;

	SendWXMessage(JSON.stringify(tSend));

	return nTotal;

}

//
function OnExit()
{	
	let ModelAll={};
	
	let ModelSelect=$("input:checked");
	let nTotal=ModelSelect.length;

	if( nTotal==0 )
	{
		ShowNotice(1);
		
		return 0;
	}
	
	for(let n=0;n<nTotal;n++)
	{
	    let OneItem=ModelSelect[n];
		
		let strModel=OneItem.getAttribute("model");
		let strVendor=OneItem.getAttribute("vendor");
		let strNozzel=OneItem.getAttribute("nozzel");
			
		//alert(strModel+strVendor+strNozzel);
		
		if(!ModelAll.hasOwnProperty(strModel))
		{
			//alert("ADD: "+strModel);
			
			ModelAll[strModel]={};
		
			ModelAll[strModel]["model"]=strModel;
			ModelAll[strModel]["nozzle_diameter"]='';
			ModelAll[strModel]["vendor"]=strVendor;
		}
		
		ModelAll[strModel]["nozzle_diameter"]+=ModelAll[strModel]["nozzle_diameter"]==''?strNozzel:';'+strNozzel;
	}
		
	var tSend={};
	tSend['sequence_id']=Math.round(new Date() / 1000);
	tSend['command']="save_userguide_models";
	tSend['data']=ModelAll;
	
	SendWXMessage( JSON.stringify(tSend) );

    return nTotal;
}


function ShowNotice( nShow )
{
	if(nShow==0)
	{
		$("#NoticeMask").hide();
		$("#NoticeBody").hide();
	}
	else
	{
		$("#NoticeMask").show();
		$("#NoticeBody").show();
	}
}

function CancelSelect()
{
	var tSend={};
	tSend['sequence_id']=Math.round(new Date() / 1000);
	tSend['command']="user_guide_cancel";
	tSend['data']={};
		
	SendWXMessage( JSON.stringify(tSend) );			
}


function ConfirmSelect()
{
	let nChoose=OnExitFilter();
	
	if(nChoose>0)
    {
		var tSend={};
		tSend['sequence_id']=Math.round(new Date() / 1000);
		tSend['command']="user_guide_finish";
		tSend['data']={};
		tSend['data']['action']="finish";
		
		SendWXMessage( JSON.stringify(tSend) );			
	}
}




