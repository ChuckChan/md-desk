# MdDesk v0.4.1 发布报告 / Release Report

**Status: ✅ COMPLETE — Completion Barrier 全部 PASS**
Generated: 2026-08-19 (本地) | Release published: 2026-08-19T08:13:14Z (UTC)

本发布为基于 v0.4.0 的**维护 / 收口修复版**，不引入 v0.5 功能、不改变 v0.4 默认行为。所有后台任务均按《Background Task Control》规范主动收割，依赖串行，Completion Barrier 全过方宣布完成。

---

## 1. Release commit SHA（发布提交）

| 字段 | 值 |
|------|-----|
| SHA | `7cf195ea37a8402ef54237b82c9c3456be5ccf60` |
| Subject | `release: MdDesk v0.4.1 (maintenance)` |
| Author | Chuck |
| Date | 2026-08-19 15:40:36 +0800 |
| 本地 HEAD | `7cf195e` ✓ |
| 远程 main (`refs/heads/main`) | `7cf195e` ✓ |

提交仅包含指定文件（10 files / +249 / -13），**未带入** `build_*/dist_*/_inspect_pyz.py/梳理与思考_*.md` 等未跟踪产物。

## 2. Tag dereference（标签解引用）

`v0.4.1` 为 **annotated tag**：
- 标签对象 SHA：`4913124bafcd34a7fa4f63c7a5cbb72ed80d9804`
- `git rev-list -n 1 v0.4.1` → 解引用到提交 `7cf195ea37a8402ef54237b82c9c3456be5ccf60` (= 发布提交) ✓
- 标签信息：`MdDesk v0.4.1 (maintenance release): YouTube batch subtitle-language wiring + single version source`

> 注：`git rev-parse v0.4.1` 返回的是**标签对象** SHA（`4913124b…`），而非提交 SHA；提交 SHA 以 `rev-list -n 1` 为准（`7cf195e`）。二者一致、无偏差。

## 3. Push status（推送状态）

- `git push origin main`：`0324e39..7cf195e` → 远程 main = `7cf195e` ✓
- `git push origin v0.4.1`（annotated）：远程 tag 存在，`refs/tags/v0.4.1` → `4913124b…` ✓

## 4. Release URL（发布页）

**https://github.com/ChuckChan/md-desk/releases/tag/v0.4.1**
（published 2026-08-19T08:13:14Z，`isDraft=null`，`isPrerelease=null`，`target_commitish=main`）

## 5. Asset name / size（资产名称 / 大小）

| 项 | 值 |
|----|-----|
| 资产名 | `MdDesk-v0.4.1-Windows-x64.zip` |
| 本地大小 | 164,865,658 字节（≈164.87 MB） |
| GitHub Release 资产大小（`gh api`） | 164,865,658 字节 — **一致** ✓ |

> 命名遵循项目历史约定（v0.4.0 / v0.3 / v0.2 均为 `MdDesk-v…-Windows-x64.zip` 带 `v` 前缀）。

## 6. SHA-256（完整性校验）

| 来源 | SHA-256 |
|------|---------|
| 本地冻结基准（verify-zip 产出） | `984fb196f3aec4014fa3e496667b5c278bdfc4c173f6cfb37ee7595d1f585df4` |
| GitHub Release 重新下载（download-sha） | `984fb196f3aec4014fa3e496667b5c278bdfc4c173f6cfb37ee7595d1f585df4` |
| **比对结果** | **MATCH = PASS** ✓ |

## 7. Background Task 最终状态（全部 PASS）

| Task ID | 阶段 | 结果 | 关键产出 |
|---------|------|------|----------|
| B84O9M | build-prod | ✅ PASS | `dist_v041/md-desk/md-desk.exe` (23,488,061 字节)，BUILD_EXIT=0 |
| fFE9af | zip-prod | ✅ PASS | ZIP 1151 文件 / 164,865,658 字节；本地 SHA 冻结基准 |
| Cd7OOq | verify-zip | ✅ PASS | SHA 一致 / STRUCTURE_OK / CONTENT_AUDIT_OK / BOOT_OK |
| — | tag + push | ✅ PASS | annotated tag `v0.4.1` 指向 `7cf195e`；main + tag 均已推送 |
| Ftg4FP | github-release | ✅ PASS | RELEASE_EXIT=0，URL 已发布，资产已上传（5m17s） |
| 6iNJ85 | download-sha | ✅ PASS | SHA_MATCH=PASS（33s，重新下载并二次计算） |

**Completion Barrier（6 条）全部 PASS → 发布完成。**

## 8. git status（工作树）

最终提交仅包含本报告文件。工作树其余为**未跟踪的发布期产物 / 辅助脚本**，均**未进入提交**：

- `build_*/`（build_md / build_mdv2 / build_rc* / build_v041 等）— PyInstaller 中间产物
- `dist_v041/`、`dist_rc_v041/` — 冻结构建 / RC 产物目录
- `_inspect_pyz.py`、`build_exe_v041.sh`、`make_dist_zip_v041.py`、`make_release_v041.sh`、`download_sha_v041.sh` — 发布辅助脚本（不提交）
- `MdDesk-v0.4.1-Windows-x64.zip` — 本地发布资产副本（不提交，已上传 GitHub）
- `*.log`（build/zip/verify/release/dl_sha）— 任务日志（不提交）
- 源码头 `src/worker.py`、`src/version.py`、`src/url_fetch_service.py`、测试、RELEASE.md、README* 已在提交 `7cf195e` 中落地

`git status --short` 仅显示上述未跟踪项，无已修改的已跟踪文件、无意外变更混入提交。

## 9. Failure → Fix → Reverify 记录

### 失败 1（首次 Release 创建）
- **现象**：`gh release create v0.4.1 ...` 返回 `RELEASE_EXIT=1`，报错 `zsh: no matches found: MdDesk-v0.4.1-Windows-x64.zip`（shell 把资产文件名当 glob 展开）；Release 实际未创建（404）。
- **连带问题**：本地产品 ZIP 当时名为 `MdDesk-0.4.1-Windows-x64.zip`（**缺 `v` 前缀**），与规范及历史约定不符。

### 修复 1
- 将产品 ZIP 重命名为 `MdDesk-v0.4.1-Windows-x64.zip`（内容不变，重算 SHA 仍为 `984fb196…`）；
- Release 创建命令加 `set -f` 关闭 glob，且 notes 与 asset 均用 **Windows 绝对路径 + 引号**，杜绝文件名被展开。

### 失败 2（重试 Release 创建）
- **现象**：重试日志被截断为单行 `START`，`gh release view` 返回 `release not found` —— 重试进程在刷新 `RELEASE_EXIT` 前被中断，Release 仍未建立。

### 修复 2
- 以**受跟踪的后台任务**（Ftg4FP）重跑 Release 创建：`set -f` + 绝对路径；`RELEASE_EXIT=0`，URL 发布成功，资产经 `gh api` 确认大小 `164865658`。

### Reverify（独立复核）
- `gh release view` + `gh api`：Release 在线，资产名/大小正确；
- `download-sha`（6iNJ85）：从 GitHub Release **重新下载**资产并二次计算 SHA-256 = `984fb196…`，与本地冻结基准**完全一致** → PASS。

---

## 结论

MdDesk v0.4.1 发布闭环**已完成且可独立复核**：
- 代码提交 `7cf195e` 已推送至 `main`，annotated tag `v0.4.1` 指向该提交并已推送；
- GitHub Release 已发布（中英双语 notes，仅维护修复），资产 `MdDesk-v0.4.1-Windows-x64.zip`（164,865,658 字节）已上传；
- 本地与 GitHub 两份资产的 SHA-256 完全一致（`984fb196f3aec4014fa3e496667b5c278bdfc4c173f6cfb37ee7595d1f585df4`）；
- 未改动功能代码 / 历史 tag / Release 文案，未进入 v0.5，未将临时文件纳入提交。

验证副本 `md-desk-v041-dl.zip`（工作区根，164MB）为 download-sha 证据，可随手删除。
