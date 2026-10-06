#!/bin/bash
set -e

# 运行脚本
echo "=========================================="
echo "YouTube News Pipeline 运行脚本"
echo "=========================================="

# 激活虚拟环境
if [ ! -d "venv" ]; then
    echo "错误: 虚拟环境不存在，请先运行 ./init.sh"
    exit 1
fi
source venv/bin/activate

# 检查配置文件
if [ ! -f "config.json" ]; then
    echo "错误: config.json 不存在，请先运行 ./init.sh 并配置"
    exit 1
fi

# 解析参数
MODE="once"
INTERVAL=300
LOG_LEVEL="INFO"
SKIP_TRANSCRIBE=false
SKIP_ARCHIVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --monitor)
            MODE="monitor"
            shift
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --skip-transcribe)
            SKIP_TRANSCRIBE=true
            shift
            ;;
        --skip-archive)
            SKIP_ARCHIVE=true
            shift
            ;;
        --help)
            echo "用法: ./run.sh [选项]"
            echo "选项:"
            echo "  --monitor              监听模式（持续运行）"
            echo "  --interval SECONDS     监听模式下的检查间隔(秒，默认300)"
            echo "  --log-level LEVEL      日志级别 DEBUG/INFO/WARNING/ERROR (默认INFO)"
            echo "  --skip-transcribe      跳过转写，直接用现有transcript.txt"
            echo "  --skip-archive         跳过归档"
            echo "  --help                 显示帮助"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 构建参数
ARGS=()
if [ "$SKIP_TRANSCRIBE" = true ]; then
    ARGS+=("--skip-transcribe")
fi
if [ "$SKIP_ARCHIVE" = true ]; then
    ARGS+=("--skip-archive")
fi
ARGS+=("--log-level" "$LOG_LEVEL")

if [ "$MODE" = "monitor" ]; then
    ARGS+=("--monitor" "--interval" "$INTERVAL")
fi

echo "运行参数: ${ARGS[@]}"
echo "=========================================="

# 运行
python3 run_pipeline.py "${ARGS[@]}"