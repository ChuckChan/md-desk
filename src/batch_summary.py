"""批次结果摘要与状态栏消息（v0.5.0 批量生产力版）。

Qt-free 的纯逻辑模块：从一组 FileEntry 的最终状态统计出批次摘要，
并生成一行中文状态栏消息。统计口径与 FileModel.data 的展示判定一致
（DONE 且 report 存在且 warnings 非空 -> 计为“质量提示”）。
"""

from dataclasses import dataclass

from .file_entry import FileStatus


@dataclass(frozen=True)
class BatchSummary:
    """一次批次转换结束后的统计摘要（不可变）。"""

    total: int          # 批次条目总数
    success: int        # DONE 条目数
    quality_hints: int  # DONE 且带质量提示（report.warnings 非空）的条目数
    failed: int         # ERROR / UNSUPPORTED 条目数
    unexecuted: int     # WAITING（未执行）条目数
    duration_ms: int    # 批次总耗时（毫秒，原样带入）


def summarize(entries: list, duration_ms: int) -> BatchSummary:
    """统计 ``entries`` 的最终状态，生成 ``BatchSummary``。

    判定口径：
      * success      = status == DONE
      * quality_hints = DONE 且 entry.report 存在且 entry.report.warnings 非空
      * failed       = status in (ERROR, UNSUPPORTED)
      * unexecuted   = status == WAITING
    """
    total = len(entries)
    success = 0
    quality_hints = 0
    failed = 0
    unexecuted = 0
    for entry in entries:
        status = getattr(entry, "status", None)
        if status == FileStatus.DONE:
            success += 1
            report = getattr(entry, "report", None)
            if report is not None and report.warnings:
                quality_hints += 1
        elif status in (FileStatus.ERROR, FileStatus.UNSUPPORTED):
            failed += 1
        elif status == FileStatus.WAITING:
            unexecuted += 1
    return BatchSummary(
        total=total,
        success=success,
        quality_hints=quality_hints,
        failed=failed,
        unexecuted=unexecuted,
        duration_ms=duration_ms,
    )


def summary_message(summary: BatchSummary, cancelled: bool = False) -> str:
    """生成一行中文批次结束消息（数字全部来自 ``summary`` 字段）。"""
    if cancelled:
        head = "已取消"
    else:
        head = "转换完成"
    return (
        f"{head}：共 {summary.total}，成功 {summary.success}"
        f"（含质量提示 {summary.quality_hints}），失败 {summary.failed}，"
        f"未执行 {summary.unexecuted}，耗时 {summary.duration_ms} ms"
    )
