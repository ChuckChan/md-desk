# MdDesk v0.5.0 发布报告

**发布日期：** 2026-08-19
**版本：** v0.5.0 (Batch Productivity / 批量生产力版)
**状态：** ✅ 发布成功

---

## 1. Release Commit / 当前 main

| 项目 | 值 |
|---|---|
| Release commit（产品代码冻结） | `6b8cd93b95d4b7e016d5e5dc61539f8e95ecf3fc` |
| 完成报告提交 | `e811f63` (docs: add MdDesk v0.5.0 completion report) |
| SHA 回填提交（HEAD） | `b4df24db989cb4875a49950e9a81df40cf3bc573` |
| 本地 main | `b4df24d` |
| Remote main | `b4df24d` ✅ 一致 |

后续提交（`e811f63`, `b4df24d`）仅含完成报告与 SHA 回填，无产品代码变更。

---

## 2. Tag 对象及 Dereference

| 项目 | 值 |
|---|---|
| Tag 名称 | `v0.5.0` |
| Tag 类型 | annotated tag |
| Tag object SHA | `0cd256e357cd076c365a1a2e7c11b843e149fa50` |
| Dereference → commit | `b4df24db989cb4875a49950e9a81df40cf3bc573`（= HEAD / remote main） |
| Release commit | `6b8cd93`（产品代码冻结点，在 tag 的 git log 范围内） |
| v0.4.1 tag → commit | `7cf195e` |
| 误指旧版本 | ❌ 未误指（v0.5.0 ≠ v0.4.1）✅ |

---

## 3. Push 状态

| 操作 | 结果 |
|---|---|
| `git push origin main` | ✅ `f29870a..b4df24d main -> main` |
| `git push origin v0.5.0` | ✅ `* [new tag] v0.5.0 -> v0.5.0` |
| Remote main SHA | `b4df24d` ✅ |
| Remote tag SHA | `0cd256e` (tag object) ✅ |

---

## 4. Release URL

- **Release URL:** https://github.com/ChuckChan/md-desk/releases/tag/v0.5.0
- **Asset download URL:** https://github.com/ChuckChan/md-desk/releases/download/v0.5.0/MdDesk-v0.5.0-Windows-x64.zip
- **isDraft:** false ✅（正式发布）
- **tagName:** v0.5.0 ✅
- **assetState:** uploaded ✅

---

## 5. 正式 ZIP 名称 / 大小

| 项目 | 值 |
|---|---|
| ZIP 文件名 | `MdDesk-v0.5.0-Windows-x64.zip` |
| ZIP 根目录 | `MdDesk-0.5.0` |
| ZIP 大小 | 164,880,155 bytes (~157.2 MB) |
| dist 内文件数 | 1,151 |
| 构建方式 | PyInstaller onedir + windowed, spec=md-desk.spec |
| 构建 venv | `D:/WB/markitdown_packaging_venv/` (Python 3.13.14, PySide6 6.11.1) |
| 构建路径 | `dist_v050/md-desk/` (workpath=build_v050) |

---

## 6. SHA-256 校验

| 来源 | SHA-256 |
|---|---|
| 本地冻结 ZIP | `0f22ed0c0b16c75143ba8f5cd6aaef2a2103321cfd65dc396ec557ce7b5b22c6` |
| GitHub Release 下载 | `0f22ed0c0b16c75143ba8f5cd6aaef2a2103321cfd65dc396ec557ce7b5b22c6` |
| **一致性** | ✅ **完全一致** |
| 下载文件大小 | 164,880,155 bytes（= 本地大小）✅ |

---

## 7. Background Task 全记录

| Task ID | 名称 | 命令 | 状态 | 耗时 | Exit Code | 日志/产物 |
|---|---|---|---|---|---|---|
| bKBVOM | Product Build | `pyinstaller --noconfirm --distpath dist_v050 --workpath build_v050 md-desk.spec` | **PASS** | 7m8s | 0 | `build_v050_log.txt`, `dist_v050/md-desk/md-desk.exe` |
| (前台) | ZIP 打包 | `python make_dist_zip_v050.py` | **PASS** | <5s | 0 | `MdDesk-v0.5.0-Windows-x64.zip`（原名缺 `v` 前缀，发布卫生收口时已重命名纠正） |
| (前台) | Verify | `python verify_dist_zip.py` | **PASS** | ~20s | 0 | SHA-256 + 结构 + 内容审计 + 启动验证 全通过 |
| (前台) | Tag 创建 | `git tag -a v0.5.0 -m "..."` | **PASS** | <1s | 0 | annotated tag → b4df24d |
| (前台) | Push main+tag | `git push origin main && git push origin v0.5.0` | **PASS** | <5s | 0 | remote main=b4df24d, tag=v0.5.0 |
| j36BGr | Release+Upload（首次） | `gh release create v0.5.0 --notes-file ... ZIP` | **FAIL** | — | 1 | 创建 Draft Release，上传 ZIP 失败（无输出） |
| (前台) | 删除 Draft | `gh release delete v0.5.0 --yes` | **PASS** | <2s | 0 | Draft 已删除 |
| (前台) | 重建 Release | `gh release create v0.5.0 --title ... --notes-file ...` | **PASS** | <3s | 0 | Release URL 获取成功 |
| j36BGr | Upload ZIP | `gh release upload v0.5.0 ZIP --clobber` | **PASS** | 5m31s | 0 | asset state=uploaded |
| 4cEZlk | Download SHA | `gh release download v0.5.0 --dir download_v050 --clobber` | **PASS** | 1m19s | 0 | 下载文件 SHA 与本地一致 |
| 3SjFnm | Upload 正确名称 ZIP | `gh release upload v0.5.0 "MdDesk-v0.5.0-Windows-x64.zip" --clobber` | **PASS** | 5m28s | 0 | correct-name asset uploaded |
| dsz8eI | Download 正确名称 SHA | `gh release download v0.5.0 --dir download_v050_renamed --pattern "MdDesk-v0.5.0-Windows-x64.zip" --clobber` | **PASS** | 1m25s | 0 | SHA-256 = 冻结值 ✅ |
| (前台) | 删除旧资产 | `gh release delete-asset v0.5.0 "MdDesk-0.5.0-Windows-x64.zip" --yes` | **PASS** | <2s | 0 | Release assetCount=1 |

**状态机汇总：** 无 WAITING / RUNNING / LOST 任务。全部 PASS。

---

## 8. 失败 → 修复 → 重验记录

### 失败 1: `gh release create` 同时上传 ZIP 失败

- **现象:** `gh release create v0.5.0 --title ... --notes-file release_notes_v050.md "MdDesk-0.5.0-Windows-x64.zip"` 返回 exit code 1，无 stdout/stderr 输出。
- **诊断:** Release 被创建为 **Draft** 状态（isDraft=true），URL 为 `untagged-ddddf6ac5c87bdcdf017`，assets 数组为空。ZIP 文件（157MB）上传未完成。
- **根因:** 大文件（157MB）与 Release 创建同时执行，可能因上传超时或连接中断导致 Release 被创建为 Draft 且资产未上传。
- **修复:**
  1. 删除 Draft Release: `gh release delete v0.5.0 --yes` → PASS
  2. 重新创建 Release（不带资产）: `gh release create v0.5.0 --title ... --notes-file ...` → PASS，获取 URL
  3. 单独上传资产: `gh release upload v0.5.0 "MdDesk-0.5.0-Windows-x64.zip" --clobber` → PASS (5m31s)
- **重验:** `gh release view v0.5.0` 确认 isDraft=false, asset state=uploaded, size=164880155 ✅

### 失败 2: `gh release download --pattern` 匹配失败

- **现象:** `gh release download v0.5.0 --pattern "MdDesk-v0.5.0-Windows-x64.zip"` 返回 "no assets match the file pattern"。
- **根因:** Asset 名称为 `MdDesk-0.5.0-Windows-x64.zip`（版本号无 `v` 前缀），pattern 中使用了 `v0.5.0` 导致不匹配。
- **修复:** 不使用 `--pattern`，直接下载所有 assets: `gh release download v0.5.0 --dir download_v050 --clobber` → PASS
- **重验:** 下载文件 SHA-256 = 本地冻结 SHA-256 ✅

### 收口修正: 资产命名纠正（release hygiene）

- **现象:** 发布后资产名为 `MdDesk-0.5.0-Windows-x64.zip`（版本号缺 `v` 前缀），与既定命名规范 `MdDesk-v0.5.0-Windows-x64.zip`（同 v0.4.0 / v0.4.1）不一致。
- **根因:** `make_dist_zip_v050.py` 中 ZIP 外部文件名使用了版本号字符串 `0.5.0` 而非 `v0.5.0`。
- **修复（不改 ZIP bytes）:** 本地 `cp "MdDesk-0.5.0-Windows-x64.zip" "MdDesk-v0.5.0-Windows-x64.zip"`（纯文件重命名，SHA-256 不变）；`gh release upload v0.5.0 "MdDesk-v0.5.0-Windows-x64.zip" --clobber` 上传正确名称资产；下载校验 SHA-256 一致后删除旧资产 `MdDesk-0.5.0-Windows-x64.zip`。
- **重验:** 下载 `MdDesk-v0.5.0-Windows-x64.zip` SHA-256 = `0f22ed0c...b5b22c6` ✅；Release 最终仅保留唯一正确名称资产 ✅

---

## 9. Git Status

工作树仅含未跟踪的发布辅助产物（build_*/dist_*/log/zip/脚本），无 modified 或 staged 文件，无产品代码变更：

```
?? build_v050/
?? build_v050_log.txt
?? dist_v050/
?? make_dist_zip_v050.py
?? release_notes_v050.md
?? download_v050/
(以及其他历史 build/dist 目录)
```

**未提交任何临时产物进仓库** ✅

---

## 10. 安全边界确认

| 边界 | 状态 |
|---|---|
| MarkItDown 版本 | 0.1.7（pinned，未升级）✅ |
| AI 默认 | OFF ✅ |
| Quality 默认 | OFF ✅ |
| SSRF 防护 | 未改动 ✅ |
| Credential Manager | 未改动 ✅ |
| OCR 安全边界 | 未改动 ✅ |
| 产品功能代码 | 冻结（6b8cd93），发布阶段零改动 ✅ |

---

## 11. 最终发布结论

**✅ 发布成功。** v0.5.0 已正式发布到 GitHub。

- Remote main = `b4df24d` ✅
- Remote tag v0.5.0 → `b4df24d` ✅
- GitHub Release published (isDraft=false) ✅
- Asset `MdDesk-v0.5.0-Windows-x64.zip` uploaded (164,880,155 bytes) ✅
- SHA-256 一致 ✅
- 所有 Background Task PASS，无 WAITING/RUNNING/LOST ✅
- 未提交临时产物 ✅
- 未修改产品代码 ✅
- 未进入 v0.6 ✅

**Release URL:** https://github.com/ChuckChan/md-desk/releases/tag/v0.5.0
