#!/data/data/com.termux/files/usr/bin/bash
# ============================================
# 小虾米 · Termux（安卓手机）一键部署脚本
# 用法：先把整个 shrimp_agent 文件夹放到手机里，
#       在 Termux 中 cd 到该目录，然后执行：
#       bash setup_termux.sh
# ============================================
set -e

echo "=================== 小虾米 Termux 部署 ==================="

# 1. 更新 Termux 包源
echo "[1/5] 更新 Termux 包..."
pkg update -y
pkg upgrade -y

# 2. 安装 Python（Termux 官方源，无需编译）
echo "[2/5] 安装 Python..."
pkg install -y python

# 3. 请求存储权限（访问 /sdcard 传文件用，可选）
echo "[3/5] 请求存储权限（可跳过）..."
termux-setup-storage || true

# 4. 安装小虾米依赖（全部纯 Python，无编译，安装快）
echo "[4/5] 安装依赖（纯 Python 版本）..."
pip install --upgrade pip
pip install -r requirements-termux.txt

# 5. 准备 .env
echo "[5/5] 检查 .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ⚠️ 已生成 .env，请编辑它填入你的 API_KEY："
    echo "     nano .env   （保存：Ctrl+O 回车，退出：Ctrl+X）"
else
    echo "  .env 已存在 ✅"
fi

echo ""
echo "=================== 部署完成 ==================="
echo ""
echo "下一步："
echo "  1) 编辑 .env 填入 API_KEY（如果还没填）"
echo "  2) 启动：  python main.py"
echo "  3) 手机浏览器打开： http://localhost:8000"
echo "     或从局域网其他设备访问： http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo ""
echo "提示："
echo "  • 让服务在后台运行： python main.py &"
echo "  • 每次开机自启可装 Termux:Boot（可选）"
