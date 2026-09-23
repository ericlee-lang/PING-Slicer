// 從本 repo 的 GUI_App.cpp 抽出「測試版資料夾首次只讀複製」的輔助函式（到 wx 相依的網頁儲存區函式之前），
// 寫到 %TEMP%\ping_dataroot_harness\seed_block.inc 給 harness.cpp 用。
// 抽的是真的那份原始碼、不是另抄一份——harness 驗的就是要上車的碼（牌 c-0924-DR-01）。
const fs = require('fs');
const path = require('path');
const os = require('os');
const src = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'src', 'slic3r', 'GUI', 'GUI_App.cpp'), 'utf8');
const b = src.indexOf('static bool ping_is_test_build()');
const e = src.indexOf('// 網頁儲存區（首頁／工作室的 WebView2）');
if (b < 0 || e < 0 || e <= b) throw new Error('錨點找不到（GUI_App.cpp 改過？）b=' + b + ' e=' + e);
const out = path.join(os.tmpdir(), 'ping_dataroot_harness');
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, 'seed_block.inc'), src.slice(b, e));
console.log('extracted →', path.join(out, 'seed_block.inc'));
