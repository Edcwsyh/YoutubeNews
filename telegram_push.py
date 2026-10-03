import json
import sys
import requests


CONFIG_FILE = "/home/Edcwsyh/work/config.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def send_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_document(bot_token, chat_id, file_path, caption=""):
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, files=files, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 2:
        print("Usage: python telegram_push.py <analysis_result.txt>")
        sys.exit(1)

    result_file = sys.argv[1]
    config = load_config()

    bot_token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")

    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        print("Error: Please set telegram_bot_token in config.json")
        sys.exit(1)
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        print("Error: Please set telegram_chat_id in config.json")
        sys.exit(1)

    with open(result_file, "r", encoding="utf-8") as f:
        content = f.read()

    max_len = 4000
    if len(content) <= max_len:
        send_message(bot_token, chat_id, f"<pre>{content}</pre>")
    else:
        send_document(bot_token, chat_id, result_file, caption="分析报告（内容过长，作为文件发送）")

    print("推送完成")


if __name__ == "__main__":
    main()