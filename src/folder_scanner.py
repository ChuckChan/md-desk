"""本地文件夹文件收集（v0.5.0 批量生产力版）。

纯标准库、Qt-free 的目录扫描工具，供 FileModel.add_folder 使用：
给定一个文件夹路径，按确定（可复现）顺序收集其下的普通文件，
目录本身永远不会作为文件返回。

语义约定：
  * 路径不存在或不是目录 -> 返回空列表（不抛异常）。
  * ``recursive=True``：使用 ``os.walk`` 递归遍历，且每层目录用
    ``dirs.sort()`` 排序、文件名用 ``sorted()`` 排序，保证跨平台 /
    跨运行的结果稳定；不跟随符号链接目录（os.walk 默认行为）。
  * ``recursive=False``：只返回该目录的直接子文件（不递归）。
"""

import os


def collect_files(path: str, recursive: bool = True) -> list[str]:
    """收集 ``path`` 目录下的普通文件绝对路径，按确定顺序返回。

    无效路径（不存在 / 非目录）返回 ``[]``。返回结果仅含普通文件，
    目录本身（含所有子目录）不会被返回。
    """
    if not path:
        return []
    if not os.path.isdir(path):
        return []
    root = os.path.abspath(path)
    out: list[str] = []
    if not recursive:
        # 只取直接子文件，用 sorted() 保证确定性。
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if os.path.isfile(full):
                out.append(full)
        return out
    # 递归遍历：顶层目录排序 + 每层文件名排序，遍历顺序确定。
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.isfile(full):
                out.append(full)
    return out
