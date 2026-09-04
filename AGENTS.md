<!-- NO-CLAUDE-BRIDGE: 本檔是 OrcaSlicer 上游的通用 repo 指南（Build／Coding Style／Testing／Commit）。PING 的正本是同目錄 CLAUDE.md（10 KB）；本檔唯一的在地教訓（Windows 別加 --parallel／PCH 吃爆 C3859）該檔已收錄，橋接只會把 3.4 KB 重複塞進每個 session 的 context。（2026-08-20 Eric 裁，牌 x-0820-PM-05） -->

> 🔴 **跨專案鐵則不在這個檔裡，而 Codex 不會自動載入它**——它的專案文件預算走到 git repo 邊界就停，
> 本 repo 是巢狀獨立 repo ⇒ 根 `D:/dev/2026claude/AGENTS.md` 不會出現在你的 context 裡。
> **開工時先把它讀一次；收工前再看一次〈收工清單〉**（那裡有你這條線要跑的檢查與推送邊界）。
> 途中特別會踩到的題目：轉態的按鈕要兩階段／跨系統變更三問與 `v_*` 契約（**改自己的 view 也要查誰在引用**）／
> 契約與治理檔的鏡像兩邊一式／新增的檢查先提示不硬擋／共用帳號可共用但守門機制不能共用／
> 靠 `max+1` 自己發號／改共用治理檔（收件匣、認領簿、待確認）的寫入協定／動共用資源要掛牌／
> 回報跨線共同編輯物要帶 commit、不要說「現在」／回報 PM 走 `PM收件匣.md` 不要 `send_message`／
> `CLAUDE.md` 第一行的 `@AGENTS.md` 橋接與文件池預算／skill 發布／D→G 發布與專案搬遷／寫檔時的內插陷阱。
> ⚠️ **這一段是指路牌，不是規則**——它列的是題目，不是條文。照這幾行做事等於沒讀過那些規則。
> ⚠️ 開不了那個路徑（權限設定擋住）＝**回報，不要當成沒有規則**。
> 📎 `D:/dev/2026claude/事故庫/20260904_Codex文件預算是共用池而且到repo邊界就停.md`

> 🔴 **本檔是 OrcaSlicer 上游的通用指南，不是 PING 這條線的正本**——PING 的正本是同目錄 `CLAUDE.md`（10 KB），Codex 同樣不會自動載入它 ⇒ **開工時一併讀一次**。

# Repository Guidelines

## Project Structure & Module Organization
OrcaSlicer’s C++17 sources live in `src/`, split by feature modules and platform adapters. User assets, icons, and printer presets are in `resources/`; translations stay in `localization/`. Tests sit in `tests/`, grouped by domain (`libslic3r/`, `sla_print/`, etc.) with fixtures under `tests/data/`. CMake helpers reside in `cmake/`, and longer references in `doc/` and `SoftFever_doc/`. Automation scripts belong in `scripts/` and `tools/`. Treat everything in `deps/` and `deps_src/` as vendored snapshots—do not modify without mirroring upstream tags.

## Build, Test, and Development Commands
Use out-of-source builds:
- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` configures dependencies and generates build files.
- `cmake --build build --target OrcaSlicer --config Release -- "/m:1" "/p:CL_MPCount=6"` compiles the app.
  ⚠ Windows 本機**不要**加 `--parallel`／`-- -m` 全平行（2026-08-04 實測：PCH 吃爆 commit → C3859/C1076 → MSBuild tracker 弄髒 → 之後「exit 0 但漏編」的 DLL 啟動即崩）；build 前先 `Get-PSDrive C` 確認 ≥15GB。細節見 `../SOP_WebView2隱形宿主與跨層協定.md` §11。
- `cmake --build build --target tests` then `ctest --test-dir build --output-on-failure` runs automated suites.
Platform helpers such as `build_linux.sh`, `build_release_macos.sh`, and `build_release_vs2022.bat` wrap the same flow with toolchain flags. Use `build_release_macos.sh -sx` when reproducing macOS build issues, and `scripts/DockerBuild.sh` for reproducible container builds.

## Coding Style & Naming Conventions
`.clang-format` enforces 4-space indents, a 140-column limit, aligned initializers, and brace wrapping for classes and functions. Run `clang-format -i <file>` before committing; the CMake `clang-format` target is available when LLVM tools are on your PATH. Prefer `CamelCase` for classes, `snake_case` for functions and locals, and `SCREAMING_CASE` for constants, matching conventions in `src/`. Keep headers self-contained and align include order with the IWYU pragmas.

## Testing Guidelines
Unit tests rely on Catch2 (`tests/catch2/`). Name specs after the component under test—for example `tests/libslic3r/TestPlanarHole.cpp`—and tag long-running cases so `ctest -L fast` remains useful. Cover new algorithms with deterministic fixtures or sample G-code stored in `tests/data/`. Document manual printer validation or regression slicer checks in your PR when automated coverage is insufficient.

## Commit & Pull Request Guidelines
The history favors concise, sentence-style subject lines with optional issue references, e.g., `Fix grid lines origin for multiple plates (#10724)`. Squash fixups locally before opening a PR. Complete `.github/pull_request_template.md`, include reproduction steps or screenshots for UI changes, and mention impacted presets or translations. Link issues via `Closes #NNNN` when applicable, and call out dependency bumps or profile migrations for maintainer review.

## Security & Configuration Tips
Follow `SECURITY.md` for vulnerability reporting. Keep API tokens and printer credentials out of tracked configs; use `sandboxes/` for experimental settings. When touching third-party code in `deps_src/`, record the upstream commit or release in your PR description and run the relevant platform build script to confirm integration.
