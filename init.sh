#!/bin/bash
set -e

echo "=========================================="
echo "YouTube News Pipeline 初始化脚本"
echo "=========================================="

# 检测操作系统
OS=$(uname -s)
echo "检测到系统: $OS"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python 版本: $PYTHON_VERSION"
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MAJOR" -eq 3 -a "$PYTHON_MINOR" -lt 10 ]; then
    echo "错误: 需要 Python 3.10+"
    exit 1
fi

# 安装系统依赖
echo ""
echo "安装系统依赖..."
if [ "$OS" = "Linux" ]; then
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y ffmpeg python3-dev python3-pip git curl
    elif command -v yum &> /dev/null; then
        sudo yum install -y ffmpeg python3-devel python3-pip git curl
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y ffmpeg python3-devel python3-pip git curl
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --needed ffmpeg python python-pip git curl
    else
        echo "警告: 无法自动安装系统依赖，请手动安装 ffmpeg python3-dev"
    fi
elif [ "$OS" = "Darwin" ]; then
    if command -v brew &> /dev/null; then
        brew install ffmpeg python3 git curl
    else
        echo "请先安装 Homebrew: https://brew.sh"
        exit 1
    fi
fi

# 检查 ffmpeg
echo ""
echo "检查 ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "错误: ffmpeg 未安装"
    exit 1
fi
ffmpeg -version | head -1

# 创建虚拟环境
echo ""
echo "创建虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "虚拟环境创建完成"
else
    echo "虚拟环境已存在"
fi

# 激活虚拟环境并安装 Python 依赖
echo ""
echo "安装 Python 依赖..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 检查配置文件
echo ""
echo "检查配置文件..."
if [ ! -f "config.json" ]; then
    echo "创建配置文件模板..."
    cat > config.json << 'EOF'
{
  "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
  "telegram_chat_id": "YOUR_CHAT_ID_HERE",
  "youtube_channels": [
    {
      "url": "https://www.youtube.com/@channel_name",
      "name": "频道名称",
      "enabled": true,
      "content_type": "all"
    }
  ]
}
EOF
    echo "已创建 config.json 模板，请填入实际配置"
else
    echo "config.json 已存在"
fi

# 检查 opencode
echo ""
echo "检查 opencode..."
if ! command -v opencode &> /dev/null; then
    echo "警告: opencode 未安装"
    echo "安装方法: 参考 https://opencode.ai/docs/installation"
else
    opencode --version
fi

echo ""
echo "=========================================="
echo "初始化完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 编辑 config.json 填入实际配置"
echo "2. 激活虚拟环境: source venv/bin/activate"
echo "3. 运行测试: python3 run_pipeline.py --skip-transcribe --skip-archive"
echo "=========================================="