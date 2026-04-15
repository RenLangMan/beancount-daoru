#!/bin/bash

cd /workspace

# 设置日志目录
LOG_DIR="build-logs"
mkdir -p "$LOG_DIR"

# 生成日志文件名
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/build-$TIMESTAMP.log"
ERROR_LOG="$LOG_DIR/build-errors-$TIMESTAMP.log"

echo "=================================="
echo "开始构建镜像"
echo "日志文件: $LOG_FILE"
echo "错误日志: $ERROR_LOG"
echo "=================================="

# 执行构建并记录日志
docker build --progress=plain \
	-f .ide/Dockerfile \
	-t docker.cnb.cool/ysundy/beancount/beancount-daoru/beancount-daoru:v1.0.1 \
	-t docker.cnb.cool/ysundy/beancount/beancount-daoru/beancount-daoru:latest \
	. 2>&1 | tee "$LOG_FILE"

# 提取错误和警告
grep -E "(ERROR|WARNING|FAILED|Step.*failed)" "$LOG_FILE" > "$ERROR_LOG" 2> /dev/null

# 显示结果
echo "=================================="
echo "构建完成！"
echo "完整日志: $LOG_FILE"
echo "错误摘要: $ERROR_LOG"
echo "=================================="

# 显示错误数量
ERROR_COUNT=$(wc -l < "$ERROR_LOG")
if [ "$ERROR_COUNT" -gt 0 ]; then
	echo "⚠️  发现 $ERROR_COUNT 条错误/警告"
	cat "$ERROR_LOG"
else
	echo "✅ 没有发现错误"
fi
