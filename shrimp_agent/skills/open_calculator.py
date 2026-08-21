import subprocess
import os

__skill_meta__ = {
    "description": "打开Windows系统自带的计算器程序（cmd calc 方式，兼容性好），支持基本使用引导。",
    "params": {
        "param": "用户的完整请求文本，可包含'打开'、'计算'、'使用'、'教程'、'帮助'等关键词，用于判断执行动作。"
    }
}


def _open_calculator():
    """
    多方式尝试打开计算器（cmd calc 优先，逐级兜底）。
    返回 (ok, msg)
    """
    # 方式1：cmd /c calc（用户指定的方式）
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "calc"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "cmd calc 方式"
    except Exception:
        pass
    # 方式2：calc.exe 直接调用（System32，PATH 内）
    try:
        subprocess.Popen(["calc.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "calc.exe 方式"
    except Exception:
        pass
    # 方式3：os.startfile
    try:
        os.startfile("calc.exe")
        return True, "startfile 方式"
    except Exception:
        pass
    # 方式4：UWP calc:
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "calc:"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "UWP calc: 方式"
    except Exception:
        pass
    return False, "所有打开方式都失败了"


def open_calculator(param: str = ''):
    """
    打开Windows计算器（cmd calc 多方式兜底），并根据param提供引导或简单计算。
    """
    result_parts = []

    # 1. 打开计算器（多方式兜底）
    ok, method = _open_calculator()
    if ok:
        result_parts.append("✅ 计算器已打开！（%s）" % method)
    else:
        result_parts.append("❌ 无法打开计算器：%s" % method)
        result_parts.append("💡 可以手动点开始菜单搜索'计算器'，或检查系统组件。")

    # 2. 根据param内容提供引导或计算
    param_lower = param.lower()

    if not param or param.strip() == '':
        result_parts.append("\n📖 计算器基本使用说明：")
        result_parts.append("1. 标准模式：进行加减乘除基本运算")
        result_parts.append("2. 科学模式：点击左上角☰菜单切换，支持三角函数、对数等")
        result_parts.append("3. 键盘输入：直接用键盘数字键和运算符输入")
        result_parts.append("4. 清除：按C键清除当前输入，CE清除当前数字")
        result_parts.append("5. 退格：按Backspace删除最后一位数字")
        result_parts.append("6. 等号：按Enter或=号得到结果")
    elif '教程' in param_lower or '帮助' in param_lower or '使用' in param_lower or '学习' in param_lower:
        result_parts.append("\n📖 计算器基本使用教程：")
        result_parts.append("• 打开计算器后，默认是标准模式")
        result_parts.append("• 基本运算：输入数字→点运算符(+,−,×,÷)→输入数字→按=")
        result_parts.append("• 键盘快捷键：+加 -减 *乘 /除 Enter等于 Esc清空")
        result_parts.append("• 切换模式：点击左上角☰图标，选择科学/程序员/日期计算等")
        result_parts.append("• 历史记录：点击右上角时钟图标可查看计算历史")
        result_parts.append("• 小技巧：按Alt+1切换到标准模式，Alt+2科学模式，Alt+3程序员模式")
    elif '计算' in param_lower or '算' in param_lower:
        import re
        expr_match = re.search(r'[0-9+\-*/().\s]+', param)
        if expr_match:
            expr = expr_match.group().strip()
            if re.fullmatch(r'[0-9+\-*/().\s]+', expr) and any(c.isdigit() for c in expr):
                try:
                    result = eval(expr)
                    result_parts.append(f"\n🧮 计算结果：{expr} = {result}")
                    result_parts.append("💡 提示：在计算器中输入同样的表达式即可验证")
                except Exception as e:
                    result_parts.append(f"\n⚠️ 计算表达式有误：{str(e)}，请直接在计算器中输入")
            else:
                result_parts.append("\n⚠️ 表达式包含非法字符，请直接在计算器中输入")
        else:
            result_parts.append("\n⚠️ 未找到计算表达式，请直接在计算器中输入数字和运算符")
    elif '打开' in param_lower:
        result_parts.append("\n✅ 计算器已为您打开，可直接开始使用！")
        result_parts.append("💡 输入'使用计算器教程'可查看详细说明")
    else:
        result_parts.append("\n📖 计算器已就绪！")
        result_parts.append("💡 您可以输入'计算器教程'查看使用说明，或直接输入算式让我帮您算")

    return "\n".join(result_parts)
