"""
自优化闭环 - 让技能越用越好

触发: 技能执行失败后（agent_loop 调用）或手动 /skills/fix

流程（五步验证链，全过才生效）:
  ① 语法编译(ast.parse)
  ② 能力约束校验(AST)：不得使用能力清单之外的硬件/API
  ③ 模拟执行 dry-run：仅对 safe=True 的模板技能（LLM 生成的不自动执行）
  ④ 备份旧版 → 原子写入 → 热重载 → 确认已加载
  ⑤ 任一步失败 → 自动回滚旧版

安全边界:
  - T0 系统核心技能: 禁止修改
  - T1 环境基础技能: 自动修复（走完整验证链）
  - T2 学习生成技能: 自动修复；连续失败≥2 次 → 停用并等待主人确认
  - 每日自动修改上限 settings.max_optimize_per_day
  - 所有修改写入审计日志 data/optimize_audit.json
"""

import ast
import hashlib
import json
import os
import re
import shutil
from datetime import datetime

from config import settings
from utils.logger import logger
from core.capability_checker import CapabilityChecker

try:
    from llm.cloud_engine import CloudEngine
except Exception:  # pragma: no cover
    CloudEngine = None

AUDIT_FILE = os.path.join(settings.base_dir, "data", "optimize_audit.json")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _extract_meta(code):
    """提取 __skill_meta__（尽力而为；用 ast.literal_eval 兼容 Python 字面量 True/None）"""
    m = re.search(r'__skill_meta__\s*=\s*(\{.*?\})', code, re.DOTALL)
    if not m:
        return {}
    try:
        return ast.literal_eval(m.group(1))
    except Exception:
        return {}


def _func_name(code):
    m = re.search(r'def\s+(\w+)\s*\(', code)
    return m.group(1) if m else None


class SelfOptimizer:
    def __init__(self, skill_manager=None, capabilities=None):
        self.skill_manager = skill_manager
        self.capabilities = capabilities or self._load_capabilities()

    def _load_capabilities(self):
        try:
            if os.path.exists(settings.capabilities_file):
                with open(settings.capabilities_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    # ---------- 审计 ----------

    def _load_audit(self):
        try:
            if os.path.exists(AUDIT_FILE):
                with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"entries": []}

    def _save_audit(self, data):
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with open(AUDIT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _audit(self, skill, error, result, reason, new_code_hash=None):
        data = self._load_audit()
        data["entries"].append({
            "time": _now(),
            "skill": skill,
            "error": (error or "")[:200],
            "result": result,          # ok | failed | rolled_back | refused
            "reason": reason,
            "code_hash": new_code_hash,
        })
        data["entries"] = data["entries"][-200:]  # 只留最近 200 条
        self._save_audit(data)

    def today_fix_count(self):
        """今日已成功修改次数（配额）"""
        return sum(
            1 for e in self._load_audit()["entries"]
            if e.get("result") == "ok" and e.get("time", "").startswith(_today())
        )

    def audit_log(self):
        return self._load_audit()

    # ---------- 核心 ----------

    def optimize_skill(self, skill_name, error, force=False):
        """
        修复一个执行失败的技能。
        返回 {"success": bool, "message": str}
        """
        if self.skill_manager is None:
            return {"success": False, "message": "未注入技能管理器"}

        if not self.skill_manager.skill_exists(skill_name):
            return {"success": False, "message": "技能 %s 不存在" % skill_name}

        tier = self.skill_manager.get_skill_tier(skill_name)

        # T0 保护
        if tier == 0:
            return {"success": False, "message": "系统核心技能禁止自动修改"}

        # 配额
        if not force and self.today_fix_count() >= settings.max_optimize_per_day:
            return {"success": False, "message": "今日自动修改已达上限（%d 次），请明天再试"
                    % settings.max_optimize_per_day}

        old_code = self.skill_manager.get_skill_code(skill_name)
        if not old_code:
            return {"success": False, "message": "读取技能源码失败"}

        logger.info("[Optimizer] 开始修复技能 %s（tier=%s）: %s", skill_name, tier, error[:80])

        # LLM 迭代修复
        new_code = self._fix_via_llm(skill_name, old_code, error)
        if not new_code:
            self._audit(skill_name, error, "failed", "LLM 修复无有效输出")
            return {"success": False, "message": "AI 修复失败，未生成有效代码"}

        # 五步验证链
        check = self._validate(new_code)
        if not check["ok"]:
            self._audit(skill_name, error, "failed", "验证未通过: %s" % check["violations"][:2])
            return {"success": False, "message": "修复版未通过验证: %s" % check["violations"][0]}

        dry = self._dry_run(new_code)
        if not dry["ok"]:
            self._audit(skill_name, error, "failed", "模拟执行失败: %s" % dry["error"])
            return {"success": False, "message": "修复版模拟执行失败: %s" % dry["error"]}

        # 备份 → 写入 → 重载
        backup = self._backup(skill_name)
        ok, msg = self._apply(skill_name, new_code)
        if not ok:
            if backup:
                self._restore(skill_name, backup)
            self._audit(skill_name, error, "rolled_back", msg)
            return {"success": False, "message": "写入失败已回滚: %s" % msg}

        digest = hashlib.md5(new_code.encode("utf-8")).hexdigest()[:8]
        self._audit(skill_name, error, "ok", "自动修复完成", digest)
        logger.info("[Optimizer] 技能 %s 修复成功 (%s)", skill_name, digest)
        return {"success": True, "message": "技能 %s 已自动修复并生效 ✅" % skill_name}

    # ---------- 修复步骤 ----------

    def _fix_via_llm(self, skill_name, old_code, error):
        if CloudEngine is None or not settings.api_key or settings.api_key == "sk-xxx":
            return None
        caps_json = json.dumps(self.capabilities, ensure_ascii=False, indent=2)
        system = (
            "你是小虾米的技能修复器。根据【环境能力清单】修复有错误的技能代码。\n\n"
            "【环境能力清单】\n%s\n\n"
            "规则：\n"
            "1. 保持函数名 %s 不变\n"
            "2. 只能使用清单内声明的硬件（from hardware import hw ...）\n"
            "3. 舵机角度在量程内、动作间隔不小于0.1秒、步数有限\n"
            "4. import 只能用标准库/清单库/hardware\n"
            "5. 函数接收 param: str = ''，返回字符串\n"
            "6. 保留 __skill_meta__\n"
            "7. 只输出 Python 代码，不要解释、不要 markdown 代码块"
            % (caps_json, skill_name)
        )
        user = "【出错的技能源码】\n%s\n\n【运行错误】\n%s\n\n请输出修复后的完整代码。" % (old_code, error)
        try:
            cloud = CloudEngine()
            result = cloud.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            code = ""
            if isinstance(result, dict):
                code = result.get("answer", "")
            elif isinstance(result, str):
                code = result
            m = re.search(r'```(?:python)?\s*(.*?)```', code, re.DOTALL)
            if m:
                code = m.group(1)
            code = code.strip()
            if not code or len(code) < 30:
                return None
            return code
        except Exception as e:
            logger.warning("[Optimizer] LLM 修复调用失败: %s", e)
            return None

    def _validate(self, code):
        """①语法 ②能力约束"""
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {"ok": False, "violations": ["语法错误: %s" % e]}
        result = CapabilityChecker(self.capabilities).check(code)
        return {"ok": result["ok"], "violations": result["violations"]}

    def _dry_run(self, code):
        """③模拟执行：只对 safe=True 的模板技能执行（避免自动运行未知代码）"""
        meta = _extract_meta(code)
        if not meta.get("safe"):
            return {"ok": True, "note": "非 safe 技能，跳过自动执行"}
        if settings.hardware_mode == "real":
            return {"ok": True, "note": "真实硬件模式，跳过模拟执行"}
        func_name = _func_name(code)
        if not func_name:
            return {"ok": True, "note": "未找到函数，跳过执行"}
        try:
            namespace = {"__name__": "_dryrun_skill"}
            exec(compile(code, "<dryrun>", "exec"), namespace)
            func = namespace.get(func_name)
            if func is None:
                return {"ok": True, "note": "函数未导出，跳过执行"}
            import inspect
            sig = inspect.signature(func)
            if any(p.default is inspect.Parameter.empty for p in sig.parameters.values()):
                return {"ok": True, "note": "函数有必填参数，跳过自动执行"}
            func()  # 无参调用，模拟器上执行安全
            return {"ok": True, "note": "模拟执行通过"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def _backup(self, skill_name):
        try:
            src = os.path.join(settings.skills_dir, skill_name + ".py")
            if not os.path.exists(src):
                return None
            backup_dir = os.path.join(settings.skills_dir, ".backups")
            os.makedirs(backup_dir, exist_ok=True)
            dst = os.path.join(backup_dir, "%s_%s.py" % (skill_name, datetime.now().strftime("%Y%m%d_%H%M%S")))
            shutil.copy2(src, dst)
            return dst
        except Exception as e:
            logger.warning("[Optimizer] 备份失败: %s", e)
            return None

    def _apply(self, skill_name, new_code):
        try:
            filepath = os.path.join(settings.skills_dir, skill_name + ".py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_code)
            self.skill_manager.reload_skills()
            if not self.skill_manager.skill_exists(skill_name):
                return False, "重载后技能丢失"
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def _restore(self, skill_name, backup_path):
        try:
            shutil.copy2(backup_path, os.path.join(settings.skills_dir, skill_name + ".py"))
            self.skill_manager.reload_skills()
            logger.info("[Optimizer] 已回滚技能 %s", skill_name)
        except Exception as e:
            logger.error("[Optimizer] 回滚失败: %s", e)

    # ---------- 停用（T2 连续失败） ----------

    def disable_skill(self, skill_name):
        """把技能文件改名 .disabled 停用，等待主人确认"""
        src = os.path.join(settings.skills_dir, skill_name + ".py")
        dst = src + ".disabled"
        try:
            if os.path.exists(src):
                os.rename(src, dst)
            self.skill_manager.reload_skills()
            return True
        except Exception as e:
            logger.error("[Optimizer] 停用技能失败: %s", e)
            return False

    def enable_skill(self, skill_name):
        """主人确认后恢复技能"""
        src = os.path.join(settings.skills_dir, skill_name + ".disabled")
        dst = src.replace(".disabled", "")
        try:
            if os.path.exists(src):
                os.rename(src, dst)
            self.skill_manager.reload_skills()
            return True
        except Exception as e:
            logger.error("[Optimizer] 恢复技能失败: %s", e)
            return False
