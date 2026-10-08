"""报告发布与归档；路径由调用者当前工作目录提供。"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


REPORTS_DIR = "reports"
ARCHIVE_DIR = "archive"


def ensure_directory(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"报告目录不能是符号链接: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_files(directory):
    """只扫描顶层非隐藏 Markdown，忽略临时目录及符号链接。"""
    return sorted(
        (path for path in Path(directory).iterdir()
         if not path.name.startswith(".") and path.suffix.lower() == ".md"
         and not path.is_symlink() and path.is_file()),
        key=lambda path: path.name,
    )


def validate_report(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"报告不是普通文件: {path}")
    if path.suffix != ".md" or path.name.startswith("."):
        raise ValueError(f"报告必须是非隐藏的 .md 文件: {path.name}")
    if any(char in '<>:"/\\|?*' or not char.isprintable() for char in path.name):
        raise ValueError(f"报告名称包含不安全字符: {path.name}")
    if len(path.name.encode("utf-8")) > 180:
        raise ValueError("报告名称过长，请缩短主题名称")
    if not path.read_text(encoding="utf-8").strip():
        raise ValueError(f"报告为空: {path.name}")


def copy_unique(source, directory, name):
    """完整写入临时文件后原子发布，同名加序号，不覆盖已有文件。"""
    directory = ensure_directory(directory)
    fd, temporary = tempfile.mkstemp(prefix=".report-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output, open(source, "rb") as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        target = directory / name
        sequence = 2
        while True:
            try:
                os.link(temporary, target)
                return target
            except FileExistsError:
                target = directory / f"{Path(name).stem}_{sequence}{Path(name).suffix}"
                sequence += 1
    finally:
        os.unlink(temporary)


def publish_report(staging_dir, reports_dir):
    """只有本次 AI 调用生成的一份完整报告可以进入待发送目录。"""
    files = list(Path(staging_dir).iterdir())
    if len(files) != 1:
        raise ValueError(f"本次任务必须生成一份 Markdown 报告，实际生成 {len(files)} 项")
    source = files[0]
    validate_report(source)
    if source.name == "analysis_result.md":
        raise ValueError("请根据内容自定义报告名称，不能使用 analysis_result.md")
    target = copy_unique(source, reports_dir, source.name)
    source.unlink()
    Path(staging_dir).rmdir()
    return str(target)


def archive_report(source, archive_dir):
    validate_report(source)
    name = f"{datetime.now():%Y%m%d}_{Path(source).name}"
    target = copy_unique(source, archive_dir, name)
    Path(source).unlink()
    return str(target)
