import json
import logging
import sys
import os
import requests


CONFIG_FILE = "/home/Edcwsyh/work/config.json"


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
    logger.info("文件发送成功")
    return resp.json()


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
    send_document(bot_token, chat_id, result_file, caption="分析报告", logger=logger)

    logger.info("推送完成")


def main():
    if len(sys.argv) < 2:
        print("Usage: python telegram_push.py <analysis_result.md> [--log-level LEVEL]")
        sys.exit(1)

    # 简单的参数解析
    result_file = sys.argv[1]
    log_level = "INFO"
    if "--log-level" in sys.argv:
        idx = sys.argv.index("--log-level")
        if idx + 1 < len(sys.argv):
            log_level = sys.argv[idx + 1]

    logger = setup_logging(getattr(logging, log_level.upper()))

    logger.info(f"开始推送: {result_file}")

    config = load_config()

    bot_token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("telegram_bot_token 未配置或为默认值")
        sys.exit(1)
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.error("telegram_chat_id 未配置或为默认值")
        sys.exit(1)

    logger.debug(f"使用 bot_token={bot_token[:10]}..., chat_id={chat_id}")

    if not os.path.exists(result_file):
        logger.error(f"文件不存在: {result_file}")
        sys.exit(1)

    with open(result_file, "r", encoding="utf-8") as f:
        content = f.read()

    max_len = 4000
    if len(content) <= max_len:
        # 转义 HTML 特殊字符，避免解析错误
        safe_content = html.escape(content)
        try:
            send_message(bot_token, chat_id, f"<pre>{safe_content}</pre>", logger=logger)
        except Exception as e:
            logger.warning(f"发送消息失败，回退为文件发送: {e}")
            send_document(bot_token, chat_id, result_file, caption="分析报告（消息发送失败，作为文件发送）", logger=logger)
    else:
        send_document(bot_token, chat_id, result_file, caption="分析报告（内容过长，作为文件发送）", logger=logger)

    logger.info("推送完成")


if __name__ == "__main__":
    main()