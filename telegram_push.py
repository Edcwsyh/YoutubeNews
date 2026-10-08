import json
import argparse
import fcntl
import hashlib
import logging
import sys
import os
import requests
from pathlib import Path

from report_files import (
    ARCHIVE_DIR, REPORTS_DIR, archive_report, ensure_directory, report_files, validate_report,
)


CONFIG_FILE = "config.json"


def setup_logging(level=logging.INFO):
    log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _handle_telegram_error(resp, action, logger):
    """处理 Telegram API 错误，返回是否为权限错误"""
    if resp.status_code == 400:
        try:
            err_data = resp.json()
            desc = err_data.get("description", "").lower()
            if "not enough rights" in desc or "forbidden" in desc or "chat not found" in desc:
                logger.error(f"{action} 失败: Bot 权限不足或 Chat ID 错误 - {err_data.get('description')}")
                logger.error("请确保：1) Bot 已加入群组/频道 2) Bot 是管理员 3) 有发送消息/文件权限 4) Chat ID 正确")
                return True  # 权限错误
        except Exception:
            pass
    logger.error(f"{action} 失败: HTTP {resp.status_code} - {resp.text}")
    return False


def send_message(bot_token, chat_id, text, logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    logger.debug(f"发送消息到 chat_id={chat_id}, 长度={len(text)}")
    resp = requests.post(url, json=payload, timeout=10)
    if resp.status_code != 200:
        if _handle_telegram_error(resp, "发送消息", logger):
            raise PermissionError("Bot 权限不足")
        resp.raise_for_status()
    logger.info("消息发送成功")
    return resp.json()


def send_document(bot_token, chat_id, file_path, caption="", logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    file_size = os.path.getsize(file_path)
    logger.debug(f"发送文件到 chat_id={chat_id}, 文件={file_path}, 大小={file_size} bytes")
    with open(file_path, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, files=files, data=data, timeout=30)
    if resp.status_code != 200:
        if _handle_telegram_error(resp, "发送文件", logger):
            raise PermissionError("Bot 权限不足")
        resp.raise_for_status()
    result = resp.json()
    if result.get("ok") is not True:
        raise RuntimeError(f"Telegram 未确认文件发送成功: {result.get('description', '未知错误')}")
    logger.info("文件发送成功")
    return result


def push_result(result_file, log_level="INFO", logger=None, config=None):
    """直接可调用的推送函数"""
    if logger is None:
        logger = setup_logging(getattr(logging, log_level.upper()))
    if config is None:
        config = load_config()

    logger.info(f"开始推送: {result_file}")

    bot_token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("telegram_bot_token 未配置或为默认值")
        raise ValueError("telegram_bot_token 未配置")
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.error("telegram_chat_id 未配置或为默认值")
        raise ValueError("telegram_chat_id 未配置")

    logger.debug(f"使用 bot_token={bot_token[:10]}..., chat_id={chat_id}")

    if not os.path.exists(result_file):
        logger.error(f"文件不存在: {result_file}")
        raise FileNotFoundError(f"文件不存在: {result_file}")

    # 始终作为文件发送
    send_document(bot_token, chat_id, result_file, caption=Path(result_file).stem[:1024], logger=logger)

    logger.info("推送完成")


def push_reports(base_dir=None, log_level="INFO", logger=None, config=None, skip_archive=False):
    """发送 reports 中的待发送报告；已确认发送的文件可只重试归档。"""
    if logger is None:
        logger = setup_logging(getattr(logging, log_level.upper()))
    base_dir = Path(base_dir or os.getcwd())
    reports_dir = ensure_directory(base_dir / REPORTS_DIR)
    receipt_file = reports_dir / ".sent.json"
    lock_file = reports_dir / ".push.lock"
    if receipt_file.is_symlink() or lock_file.is_symlink():
        raise ValueError("报告发送状态文件不能是符号链接")

    with lock_file.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.error("已有报告发送任务运行中，本次不重复发送")
            return False
        receipts = json.loads(receipt_file.read_text(encoding="utf-8")) if receipt_file.exists() else {}
        if not isinstance(receipts, dict):
            raise ValueError("报告发送状态格式错误")

        def save_receipts():
            temporary = reports_dir / ".sent.json.tmp"
            if temporary.is_symlink():
                raise ValueError("报告发送状态临时文件不能是符号链接")
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(receipts, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, receipt_file)

        files = report_files(reports_dir)
        if not files:
            logger.info("reports 中没有待发送的 Markdown 报告")
            return True
        all_success = True
        for path in files:
            try:
                validate_report(path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if receipts.get(path.name) != digest:
                    if config is None:
                        config = load_config()
                    push_result(str(path), log_level=log_level, logger=logger, config=config)
                    # 先记录成功，再归档；归档失败时下次不重复发送。
                    receipts[path.name] = digest
                    save_receipts()
                else:
                    logger.info(f"已确认发送，跳过重复推送: {path.name}")
                if not skip_archive:
                    archived = archive_report(path, base_dir / ARCHIVE_DIR)
                    logger.info(f"报告已归档: {archived}")
                    receipts.pop(path.name, None)
                    save_receipts()
            except Exception as e:
                logger.error(f"报告发送或归档失败，保留待重试: {path.name}: {e}")
                all_success = False
        return all_success


def main():
    parser = argparse.ArgumentParser(description="发送 reports 中的全部 Markdown 报告，成功后归档")
    parser.add_argument("result_file", nargs="?", help="可选：只发送指定文件，不扫描目录、不归档")
    parser.add_argument("--skip-archive", action="store_true", help="已发送报告保留在 reports，不重复发送")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logger = setup_logging(getattr(logging, args.log_level))
    try:
        if args.result_file:
            push_result(args.result_file, log_level=args.log_level, logger=logger)
            success = True
        else:
            success = push_reports(log_level=args.log_level, logger=logger, skip_archive=args.skip_archive)
    except Exception as e:
        logger.error(f"发送任务失败: {e}")
        success = False
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
