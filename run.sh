#!/bin/bash
set -e

# 激活虚拟环境
source venv/bin/activate

# 直接运行，固定参数
python3 run_pipeline.py --monitor --interval 1800 --log-level DEBUG