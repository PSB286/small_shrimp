"""
动作引擎 - 姿态序列播放

"跑"、"跳舞"、"摇尾巴" 在数据层面都是：一系列姿态 + 时间间隔。
姿态 = {舵机id: 角度}。动作引擎负责按顺序执行并校验舵机合法性。

技能代码可以这样写：
    poses = [
        {"leg_fl": 45, "leg_fr": 0, "leg_bl": 0, "leg_br": 45},
        {"leg_fl": 0,  "leg_fr": 45, "leg_bl": 45, "leg_br": 0},
    ]
    hw.play_poses(poses, interval=0.25)
"""

import time

from hardware.simulator import SIM_STATE


def validate_poses(poses, servo_ids):
    """校验姿态序列：舵机 id 必须存在、角度必须在量程内。返回错误列表"""
    errors = []
    known = set(servo_ids)
    for i, pose in enumerate(poses):
        if not isinstance(pose, dict):
            errors.append("第 %d 个姿态不是字典" % i)
            continue
        for servo_id, angle in pose.items():
            if servo_id not in known:
                errors.append("姿态 %d 引用了未知舵机 '%s'（可用: %s）"
                              % (i, servo_id, sorted(known)))
    return errors


def play_poses(hw, poses, interval=0.3):
    """
    播放姿态序列。
    hw: Hardware 实例（提供 servo() 与 servo_ids）
    返回播放的步数；任何一步出错都会抛出 ValueError（由自优化循环捕获）
    """
    if not poses:
        return 0
    errors = validate_poses(poses, hw.servo_ids)
    if errors:
        raise ValueError("动作序列不合法: " + "; ".join(errors[:5]))

    step = 0
    for pose in poses:
        for servo_id, angle in pose.items():
            hw.servo(servo_id).set_angle(angle)
        step += 1
        if interval and interval > 0:
            time.sleep(interval)
    return step
