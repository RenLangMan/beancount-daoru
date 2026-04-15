#!/bin/bash
echo "🧹 清理 llama-server 进程和端口..."

# 杀死所有 llama-server 进程
echo "停止 llama-server 进程..."
pkill -9 -f llama-server 2> /dev/null || true

# 清理特定端口
for port in 1314 9527 8080; do
	if lsof -i:"$port" > /dev/null 2>&1; then
		echo "清理端口 $port..."
		# 修复 SC2046: 使用 xargs 或数组来安全处理
		lsof -t -i:"$port" 2> /dev/null | xargs -r kill -9
	fi
done

# 清理 pytest-xprocess 缓存
echo "清理 pytest 缓存..."
rm -rf .pytest_cache/d/.xprocess/

# 清理 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2> /dev/null || true

echo "✅ 清理完成"

# 显示当前状态
echo ""
echo "当前 llama-server 进程:"
# 修复 SC2009: 使用 pgrep 替代 ps | grep
if pgrep -f llama-server > /dev/null 2>&1; then
	pgrep -af llama-server
else
	echo "无"
fi

echo ""
echo "当前端口占用:"
netstat -tlnp 2> /dev/null | grep -E "1314|9527|8080" || echo "端口 1314, 9527, 8080 已释放"
