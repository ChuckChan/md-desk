"""批量导出 Markdown 到指定目录（v0.5.0 批量生产力版）。

Qt-free、MarkItDown-free 的纯逻辑模块：把一组 FileEntry 中已完成
（DONE）且带有 markdown 的条目，按 `文件名去掉扩展名 + ".md"` 写入
目标目录。

命名与覆盖规则（docstring 内写清，便于后续维护）：
  * 目标文件名：``Path(entry.filename).stem + ".md"``。
  * 批内重名去重：按候选行序依次生成；若目标名已被本批前面的条目
    占用，则追加 ``_2``、``_3`` … 直到唯一（如 ``a.md``、``a_2.md``）。
  * 禁止覆盖源文件：若目标绝对路径等于**任一候选条目**的源文件
    绝对路径（URL 条目的 ``path`` 是 URL，不可能撞上），该条目计入
    ``skipped_conflict`` 且不写入。
  * 目标已存在于磁盘但**不是**源文件 -> 正常覆盖（标准导出语义）。
  * 任何单条写入失败（OSError 等）都不中断整体流程：该条目计入
    ``failed``（计数完整），错误消息截断到约 120 字符存入 ``errors``
    （最多保留 5 条）。整个函数永不 raise。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from .file_entry import FileStatus


@dataclass(frozen=True)
class ExportResult:
    """一次批量导出的汇总结果（不可变）。"""

    exported: int                 # 实际成功写入的条目数
    skipped_conflict: int         # 因目标为源文件而被跳过的条目数
    failed: int                   # 写入失败的条目数（完整计数）
    errors: tuple[str, ...]       # 截断后的错误消息（最多 5 条）
    exported_paths: tuple[str, ...]  # 按候选顺序、实际写入的绝对路径


def export_batch(entries: list, out_dir: str) -> ExportResult:
    """把 ``entries`` 中 DONE 且带 markdown 的条目导出到 ``out_dir``。

    永不 raise：所有 I/O 均在 try/except 内处理。返回 ``ExportResult``
    携带完整统计与已写入路径（按候选顺序）。
    """
    exported = 0
    skipped_conflict = 0
    failed = 0
    errors: list[str] = []
    exported_paths: list[str] = []
    used_targets: set[str] = set()

    candidates = [
        e for e in entries
        if getattr(e, "status", None) == FileStatus.DONE and e.markdown
    ]
    # 源文件绝对路径集合（用于“禁止覆盖源文件”判断）。
    # normcase 规范化：Windows 路径大小写不敏感，与批内去重口径一致。
    source_abs = {os.path.normcase(os.path.abspath(e.path)) for e in candidates}

    for entry in candidates:
        base = Path(entry.filename).stem
        name = base + ".md"
        counter = 2
        # 批内重名去重：按候选行序生成唯一目标名。
        while True:
            target = os.path.join(out_dir, name)
            key = os.path.normcase(os.path.abspath(target))
            if key in used_targets:
                name = f"{base}_{counter}.md"
                counter += 1
                continue
            used_targets.add(key)
            break
        target_abs = os.path.abspath(target)
        # 禁止覆盖源文件（URL 条目的 path 是 URL，不可能相等）。
        if os.path.normcase(target_abs) in source_abs:
            skipped_conflict += 1
            continue
        try:
            Path(target).write_text(entry.markdown, encoding="utf-8")
        except (OSError, UnicodeError) as exc:  # noqa: BLE001 - 单条失败不中断整体导出
            failed += 1
            if len(errors) < 5:
                errors.append(str(exc)[:120])
            continue
        exported += 1
        exported_paths.append(target_abs)

    return ExportResult(
        exported=exported,
        skipped_conflict=skipped_conflict,
        failed=failed,
        errors=tuple(errors),
        exported_paths=tuple(exported_paths),
    )
