from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger, AstrBotConfig
import time
import re
import json
import asyncio
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque


class SleepPlugin(Star):
    """睡觉插件 - 让 bot 暂时保持安静"""
    
    # 时间单位转换(秒)
    TIME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 从配置读取优先级
        self.plugin_priority = config.get("priority", 10000)

        self.wake_prefix: list[str] = self.context.get_config().get("wake_prefix", [])
        # 直接获取配置项中的列表
        self.sleep_cmds = config.get("sleep_commands", ["睡觉", "sleep"])
        self.wake_cmds = config.get("wake_commands", ["起床", "醒来", "wake"])
        self.unlock_cmd = config.get("unlock_command", "解锁")
        self.require_prefix = config.get("require_prefix", False)
        
        # 分离的权限配置
        self.sleep_require_admin = config.get("sleep_require_admin", False)
        self.wake_require_admin = config.get("wake_require_admin", False)
        
        # 敏感锁定配置
        self.lock_secret = config.get("lock_secret", "astrbot_sleep_secret")
        self.unlock_code_input = config.get("unlock_code_input", "")  # 用户输入的解锁码
        self.clear_lock_on_startup = config.get("clear_lock_on_startup", True)  # 启动时清空锁定记录
        self.unlock_code_interval = config.get("unlock_code_interval", 60)  # 解锁码有效期（秒）
        self.enable_force_unlock = config.get("enable_force_unlock", True)  # 启用强制解锁
        
        # 锁定提醒记录 {origin: last_unlock_code} 用于判断解锁码是否变化
        self.locked_last_code: dict[str, str] = {}
        
        # 锁定提示模板
        self.lock_reply_template = config.get(
            "lock_reply_template",
            "🔒 当前群已被锁定\n原因: {reason}\n锁定时间: {lock_time}\n\n解锁码: {unlock_code}\n有效期至: {unlock_code_expiry}\n\n请在后台配置文件中输入解锁码并保存后，由管理员发送「{unlock_command}」指令解锁。"
        )
        self.locked_reply_template = config.get(
            "locked_reply_template",
            "🔒 当前群已被锁定\n原因: {reason}\n\n解锁码: {unlock_code}\n有效期至: {unlock_code_expiry}\n\n请在后台配置文件中输入正确的解锁码后，由管理员发送解锁指令"
        )
        
        # 支持字符串配置，转换为列表
        if isinstance(self.sleep_cmds, str):
            self.sleep_cmds = re.split(r"[\s,]+", self.sleep_cmds)
        if isinstance(self.wake_cmds, str):
            self.wake_cmds = re.split(r"[\s,]+", self.wake_cmds)

        # 时长配置
        self.default_duration = self._get_duration_config("default_duration", 600, 60, 86400)
        self.max_duration_command = self._get_duration_config("max_duration_command", 43200, 60, 86400)
        self.max_duration_auto = self._get_duration_config("max_duration_auto", 10800, 60, 86400)

        self.sleep_reply = config.get("sleep_reply", "好的，我去睡觉了~💤")
        self.wake_reply = config.get("wake_reply", "早安~我醒来了☀️")

        # 群昵称更新配置
        self.group_card_enabled = config.get("group_card_update_enabled", False)
        self.group_card_template = config.get(
            "group_card_template", "{original_name}[睡觉中 {remaining}]"
        )
        self.group_card_template_auto = config.get(
            "group_card_template_auto", "{original_name}[静默中 {remaining}]"
        )
        self.group_card_template_locked = config.get(
            "group_card_template_locked", "{original_name}[已锁定]"
        )
        self.original_group_cards = {}
        self.original_nicknames = {}
        self.origin_to_event_map = {}
        self._update_task = None

        # 定时睡觉配置
        self.scheduled_enabled = config.get("scheduled_sleep_enabled", False)
        self.scheduled_times_text = config.get("scheduled_sleep_times", "23:00-07:00")
        self.scheduled_time_ranges = self._parse_time_ranges(self.scheduled_times_text)

        # 刷屏检测配置
        self.spam_detect_enabled = config.get("spam_detect_enabled", False)
        self.spam_threshold = config.get("spam_threshold", 10)
        self.spam_window = config.get("spam_window", 60)
        self.spam_auto_sleep_duration = config.get("spam_auto_sleep_duration", 1800)
        
        # 群消息计数器
        self.message_counters: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 自动解开的睡觉记录
        self.auto_wake_sleep_map: dict[str, dict] = {}
        
        # 敏感锁定记录 {origin: {"reason": str, "lock_time": float, "unlock_code": str}}
        self.locked_origins: dict[str, dict] = {}

        self.sleep_map = {}
        self.data_dir = (
            Path(__file__).parent.parent.parent
            / "plugin_data"
            / "astrbot_plugin_sleep"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_map_path = self.data_dir / "sleep_map.json"
        self.locked_path = self.data_dir / "locked.json"
        self._load_sleep_map()
        self._load_locked_map()

        # 后台任务
        self._update_task = None
        self._update_task_started = False
        self._auto_wake_task = None
        self._auto_wake_task_started = False

        # 日志输出
        log_parts = [
            f"指令: {self.sleep_cmds} & {self.wake_cmds}",
            f"默认时长: {self._format_duration(self.default_duration)}",
            f"指令最大: {self._format_duration(self.max_duration_command)}",
            f"自判定最大: {self._format_duration(self.max_duration_auto)}",
            f"优先级: {self.plugin_priority}",
        ]
        
        if self.sleep_require_admin:
            log_parts.append("睡觉需管理员")
        if self.wake_require_admin:
            log_parts.append("起床需管理员")
            
        if self.scheduled_enabled:
            time_ranges_str = ", ".join(
                [f"{start}-{end}" for start, end in self.scheduled_time_ranges]
            )
            log_parts.append(f"定时: {time_ranges_str}")
            
        if self.spam_detect_enabled:
            log_parts.append(f"刷屏检测: {self.spam_threshold}条/{self.spam_window}s → {self._format_duration(self.spam_auto_sleep_duration)}")
            
        logger.info(f"[Sleep] 已加载 | " + " | ".join(log_parts))

        if self.group_card_enabled:
            logger.info(f"[Sleep] 群昵称更新已启用 | 普通模板: {self.group_card_template} | 自动模板: {self.group_card_template_auto} | 锁定模板: {self.group_card_template_locked}")

    def _generate_unlock_code(self, group_id: str, timestamp: float = None) -> str:
        """生成基于群号和时间戳的6位解锁码（TOTP风格）
        
        使用 HMAC-SHA256 算法，基于群号、时间戳和密钥生成
        解锁码会随时间变化，增加安全性
        
        Args:
            group_id: 群号
            timestamp: 时间戳，默认使用当前时间
        """
        if timestamp is None:
            timestamp = time.time()
        
        # 计算时间步长（每 interval 秒变化一次）
        time_step = int(timestamp // self.unlock_code_interval)
        
        data = f"{group_id}:{time_step}:{self.lock_secret}"
        hash_value = hashlib.sha256(data.encode()).hexdigest()
        code = int(hash_value[:8], 16) % 1000000
        return f"{code:06d}"

    def _get_unlock_code_expiry(self, timestamp: float = None) -> str:
        """获取解锁码到期时间
        
        Args:
            timestamp: 当前时间戳，默认使用当前时间
            
        Returns:
            到期时间字符串，格式: YYYY-MM-DD HH:MM:SS
        """
        if timestamp is None:
            timestamp = time.time()
        
        # 计算当前时间步的结束时间
        time_step = int(timestamp // self.unlock_code_interval)
        expiry_timestamp = (time_step + 1) * self.unlock_code_interval
        
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_timestamp))

    def _verify_unlock_code(self, group_id: str, code: str) -> bool:
        """验证解锁码是否正确
        
        支持当前时间步和前一个时间步的解锁码（允许一定的时间误差）
        """
        current_time = time.time()
        
        # 检查当前时间步
        expected_code = self._generate_unlock_code(group_id, current_time)
        if hmac.compare_digest(code, expected_code):
            return True
        
        # 检查前一个时间步（允许时间误差）
        prev_time = current_time - self.unlock_code_interval
        prev_code = self._generate_unlock_code(group_id, prev_time)
        if hmac.compare_digest(code, prev_code):
            return True
        
        return False

    def _get_duration_config(self, key: str, default: int, min_val: int, max_val: int) -> int:
        """获取时长配置并验证范围"""
        value = self.config.get(key, default)
        if not isinstance(value, (int, float)) or not (min_val <= value <= max_val):
            logger.warning(
                f"[Sleep] ⚠️ {key} 配置无效({value})，使用默认值 {default}s"
            )
            self.config[key] = default
            self.config.save_config()
            return default
        return int(value)

    def _format_duration(self, seconds: int) -> str:
        """格式化时长显示"""
        if seconds >= 3600:
            return f"{seconds / 3600:.1f}小时"
        elif seconds >= 60:
            return f"{seconds // 60}分钟"
        else:
            return f"{seconds}秒"

    def _format_remaining_time(self, seconds: int) -> str:
        """格式化剩余时间显示"""
        if seconds <= 0:
            return "0分钟"
        
        hours = seconds / 3600
        if hours >= 1:
            return f"{hours:.1f}小时"
        else:
            minutes = seconds / 60
            return f"{int(minutes)}分钟"

    def _parse_time_ranges(self, time_text: str) -> list[tuple[str, str]]:
        """解析时间范围文本"""
        time_ranges = []

        for line in time_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", line)
            if not match:
                logger.warning(f"[Sleep] ⚠️ 无法解析时间范围: {line}")
                continue

            start_time, end_time = match.groups()
            try:
                datetime.strptime(start_time, "%H:%M")
                datetime.strptime(end_time, "%H:%M")
                time_ranges.append((start_time, end_time))
            except ValueError:
                logger.warning(f"[Sleep] ⚠️ 无效的时间格式: {line}")

        if not time_ranges and self.scheduled_enabled:
            logger.warning("[Sleep] ⚠️ 未配置有效的定时时间段，定时睡觉将不会生效")

        return time_ranges

    def _load_sleep_map(self):
        try:
            if self.sleep_map_path.exists():
                with open(self.sleep_map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                if isinstance(data, dict):
                    if all(isinstance(v, (int, float)) for v in data.values()):
                        self.sleep_map = {k: float(v) for k, v in data.items()}
                    else:
                        self.sleep_map = {}
                        for k, v in data.items():
                            if isinstance(v, dict):
                                self.sleep_map[k] = float(v.get("expiry", 0))
                                if "auto_wake_threshold" in v:
                                    self.auto_wake_sleep_map[k] = v
                            else:
                                self.sleep_map[k] = float(v)
                                
                if self.sleep_map:
                    logger.info(f"[Sleep] 加载了 {len(self.sleep_map)} 条睡觉记录")
        except Exception as e:
            logger.warning(f"[Sleep] ⚠️ 加载睡觉记录失败: {e}")

    def _load_locked_map(self):
        """加载敏感锁定记录"""
        try:
            if self.locked_path.exists():
                with open(self.locked_path, "r", encoding="utf-8") as f:
                    self.locked_origins = json.load(f)
                    
                # 兜底：启动时清空锁定记录（可配置）
                if self.clear_lock_on_startup and self.locked_origins:
                    logger.info(f"[Sleep] 🔄 启动时清空 {len(self.locked_origins)} 条敏感锁定记录（兜底机制）")
                    self.locked_origins = {}
                    self._save_locked_map()
                elif self.locked_origins:
                    logger.info(f"[Sleep] 加载了 {len(self.locked_origins)} 条敏感锁定记录")
                    logger.warning(f"[Sleep] ⚠️ 检测到锁定记录！如需清空，请设置 clear_lock_on_startup=true 并重启，或手动删除 {self.locked_path}")
        except Exception as e:
            logger.warning(f"[Sleep] ⚠️ 加载敏感锁定记录失败: {e}")
            # 出错时清空锁定记录，防止卡死
            self.locked_origins = {}
            self._save_locked_map()

    def _save_sleep_map(self):
        try:
            data = {}
            for k, v in self.sleep_map.items():
                if k in self.auto_wake_sleep_map:
                    data[k] = self.auto_wake_sleep_map[k]
                else:
                    data[k] = v
                    
            with open(self.sleep_map_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[Sleep] ⚠️ 保存睡觉记录失败: {e}")

    def _save_locked_map(self):
        """保存敏感锁定记录"""
        try:
            with open(self.locked_path, "w", encoding="utf-8") as f:
                json.dump(self.locked_origins, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[Sleep] ⚠️ 保存敏感锁定记录失败: {e}")

    def _is_in_scheduled_time(self) -> bool:
        """检查当前时间是否在定时睡觉时间段内"""
        if not self.scheduled_enabled or not self.scheduled_time_ranges:
            return False

        current_minutes = datetime.now().hour * 60 + datetime.now().minute

        for start_time_str, end_time_str in self.scheduled_time_ranges:
            start_h, start_m = map(int, start_time_str.split(":"))
            end_h, end_m = map(int, end_time_str.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            in_range = (
                start_minutes <= current_minutes <= end_minutes
                if start_minutes <= end_minutes
                else current_minutes >= start_minutes or current_minutes < end_minutes
            )
            if in_range:
                return True

        return False

    def _check_prefix(self, event: AstrMessageEvent) -> bool:
        """检查消息是否满足前缀要求"""
        if not self.require_prefix:
            return True

        chain = event.get_messages()
        if not chain:
            return False

        first_seg = chain[0]
        if isinstance(first_seg, Comp.Plain):
            return any(first_seg.text.startswith(prefix) for prefix in self.wake_prefix)
        elif isinstance(first_seg, Comp.At):
            return str(first_seg.qq) == str(event.get_self_id())
        else:
            return False

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否是管理员"""
        try:
            astrbot_config = self.context.get_config()
            admins = []
            if hasattr(astrbot_config, 'get'):
                admins = astrbot_config.get("admins_id", [])
            elif isinstance(astrbot_config, dict):
                admins = astrbot_config.get("admins_id", [])
            
            sender_id = event.get_sender_id()
            is_admin = str(sender_id) in [str(admin) for admin in admins]
            
            return is_admin
        except Exception as e:
            logger.error(f"[Sleep] 检查管理员权限时出错: {e}")
            return False

    def _update_message_counter(self, origin: str) -> int:
        """更新消息计数器，返回当前窗口内的消息数"""
        now = time.time()
        counter = self.message_counters[origin]
        
        while counter and counter[0] < now - self.spam_window:
            counter.popleft()
        
        counter.append(now)
        
        return len(counter)

    def _get_message_rate(self, origin: str) -> int:
        """获取当前窗口内的消息数"""
        now = time.time()
        counter = self.message_counters[origin]
        
        while counter and counter[0] < now - self.spam_window:
            counter.popleft()
        
        return len(counter)

    async def _update_group_card(
        self, event: AstrMessageEvent, origin: str, remaining_seconds: int, 
        is_auto_sleep: bool = False, is_locked: bool = False
    ) -> None:
        """更新群昵称显示剩余时长"""
        if not self.group_card_enabled:
            return

        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            if not isinstance(event, AiocqhttpMessageEvent):
                return
        except ImportError:
            return

        group_id = event.get_group_id()
        if not group_id:
            return

        bot = getattr(event, "bot", None)
        if not bot or not hasattr(bot, "call_action"):
            return

        self_id = event.get_self_id()
        if not self_id:
            return

        try:
            if origin not in self.original_group_cards:
                try:
                    member_info = await bot.call_action(
                        "get_group_member_info",
                        group_id=int(group_id),
                        user_id=int(self_id),
                        no_cache=True,
                    )
                    self.original_group_cards[origin] = member_info.get("card", "") or ""
                    self.original_nicknames[origin] = member_info.get("nickname", "") or ""
                except Exception as e:
                    logger.debug(f"[Sleep] 获取原始群昵称失败: {e}")
                    self.original_group_cards[origin] = ""
                    self.original_nicknames[origin] = ""

            original_card = self.original_group_cards.get(origin, "")
            original_nickname = self.original_nicknames.get(origin, "")
            original_name = original_card if original_card else original_nickname
            
            # 根据状态选择模板
            if is_locked:
                template = self.group_card_template_locked
                try:
                    card = template.format(
                        original_card=original_card,
                        original_nickname=original_nickname,
                        original_name=original_name,
                    )
                except KeyError:
                    card = f"{original_name}[已锁定]"
            elif remaining_seconds > 0:
                remaining_str = self._format_remaining_time(remaining_seconds)
                template = self.group_card_template_auto if is_auto_sleep else self.group_card_template

                try:
                    card = template.format(
                        remaining=remaining_str,
                        remaining_seconds=remaining_seconds,
                        original_card=original_card,
                        original_nickname=original_nickname,
                        original_name=original_name,
                    )
                except KeyError as e:
                    logger.warning(f"[Sleep] 群昵称模板占位符错误: {e}")
                    card = f"[{'静默' if is_auto_sleep else '睡觉'}中 {remaining_str}]"
            else:
                card = self.original_group_cards.get(origin, "")

            await bot.call_action(
                "set_group_card",
                group_id=int(group_id),
                user_id=int(self_id),
                card=card[:60],
            )
            logger.debug(f"[Sleep] 已更新群昵称: {card[:60]}")

        except Exception as e:
            logger.warning(f"[Sleep] 更新群昵称失败: {e}")

    async def _ensure_update_task_started(self) -> None:
        """确保群昵称更新任务已启动"""
        if self.group_card_enabled and not self._update_task_started:
            self._update_task_started = True
            self._update_task = asyncio.create_task(self._group_card_update_loop())
            logger.info("[Sleep] 群昵称更新任务已启动")

    async def _group_card_update_loop(self) -> None:
        """定时更新群昵称的后台任务"""
        try:
            while True:
                await asyncio.sleep(60)

                if not self.sleep_map and not self.locked_origins:
                    continue

                current_time = time.time()
                
                # 更新睡觉状态的群昵称
                for origin, expiry in list(self.sleep_map.items()):
                    remaining_seconds = int(expiry - current_time)
                    if remaining_seconds > 0:
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            is_auto = origin in self.auto_wake_sleep_map
                            await self._update_group_card(event, origin, remaining_seconds, is_auto)
                    else:
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            await self._update_group_card(event, origin, 0, False)
                        self.original_group_cards.pop(origin, None)
                        self.original_nicknames.pop(origin, None)
                        self.origin_to_event_map.pop(origin, None)
                        self.sleep_map.pop(origin, None)
                        self.auto_wake_sleep_map.pop(origin, None)
                        self._save_sleep_map()
                        logger.info(f"[Sleep] ⏰ 睡觉已自动结束 | 来源: {origin}")

        except asyncio.CancelledError:
            logger.info("[Sleep] 群昵称更新任务已停止")
        except Exception as e:
            logger.error(f"[Sleep] 群昵称更新任务异常: {e}")

    async def _ensure_auto_wake_task_started(self) -> None:
        """确保自动解开检测任务已启动"""
        if not self._auto_wake_task_started:
            self._auto_wake_task_started = True
            self._auto_wake_task = asyncio.create_task(self._auto_wake_check_loop())
            logger.info("[Sleep] 自动解开检测任务已启动")

    async def _auto_wake_check_loop(self) -> None:
        """定时检测是否满足自动解开条件"""
        try:
            while True:
                await asyncio.sleep(10)

                if not self.auto_wake_sleep_map:
                    continue

                current_time = time.time()
                for origin, config in list(self.auto_wake_sleep_map.items()):
                    expiry = config.get("expiry", 0)
                    if current_time >= expiry:
                        await self._auto_wake(origin, "睡觉时间已到")
                        continue

                    threshold = config.get("auto_wake_threshold", 0)
                    if threshold > 0:
                        rate = self._get_message_rate(origin)
                        if rate < threshold:
                            await self._auto_wake(origin, f"群消息速率已降至 {rate} 条/{self.spam_window}s")

        except asyncio.CancelledError:
            logger.info("[Sleep] 自动解开检测任务已停止")
        except Exception as e:
            logger.error(f"[Sleep] 自动解开检测任务异常: {e}")

    async def _auto_wake(self, origin: str, reason: str) -> None:
        """自动解开睡觉状态"""
        if origin not in self.sleep_map:
            return
            
        config = self.auto_wake_sleep_map.get(origin, {})
        
        self.sleep_map.pop(origin, None)
        self.auto_wake_sleep_map.pop(origin, None)
        self._save_sleep_map()

        if self.group_card_enabled:
            event = self.origin_to_event_map.get(origin)
            if event:
                await self._update_group_card(event, origin, 0, False)
            self.original_group_cards.pop(origin, None)
            self.original_nicknames.pop(origin, None)
            self.origin_to_event_map.pop(origin, None)

        logger.info(f"[Sleep] 🌅 自动起床 | 来源: {origin} | 原因: {reason}")
        
        try:
            event = self.origin_to_event_map.get(origin)
            if event:
                from astrbot.api.event import MessageChain
                chain = MessageChain().message(f"🌅 {reason}，我醒来了~")
                await self.context.send_message(origin, chain)
        except Exception as e:
            logger.debug(f"[Sleep] 发送自动起床通知失败: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def handle_message(self, event: AstrMessageEvent):
        text = event.get_message_str().strip()
        origin = event.unified_msg_origin

        if self.spam_detect_enabled:
            self._update_message_counter(origin)

        # 检查是否是敏感锁定状态
        if origin in self.locked_origins:
            lock_info = self.locked_origins.get(origin, {})
            group_id = lock_info.get("group_id", "")
            
            # 检查是否是解锁指令
            if text.startswith(self.unlock_cmd):
                if not self._check_admin(event):
                    yield event.plain_result("⚠️ 只有管理员才能解锁")
                    event.stop_event()
                    return
                
                # 检查配置文件中的解锁码
                if not self.unlock_code_input:
                    # 发送当前解锁码提示
                    current_code = self._generate_unlock_code(str(group_id)) if group_id else "??????"
                    expiry = self._get_unlock_code_expiry()
                    yield event.plain_result(f"⚠️ 请先在配置文件中输入解锁码\n\n当前解锁码: {current_code}\n有效期至: {expiry}")
                    event.stop_event()
                    return
                
                # 获取群号
                if not group_id:
                    yield event.plain_result("⚠️ 无法获取群信息")
                    event.stop_event()
                    return
                
                # 验证解锁码
                if self._verify_unlock_code(str(group_id), self.unlock_code_input):
                    # 解锁成功
                    self.locked_origins.pop(origin, {})
                    self.locked_last_code.pop(origin, None)
                    self._save_locked_map()
                    
                    # 清除配置中的解锁码
                    self.config["unlock_code_input"] = ""
                    self.config.save_config()
                    self.unlock_code_input = ""
                    
                    # 恢复群昵称
                    if self.group_card_enabled:
                        await self._update_group_card(event, origin, 0, False, False)
                        self.original_group_cards.pop(origin, None)
                        self.original_nicknames.pop(origin, None)
                    
                    logger.info(f"[Sleep] 🔓 敏感锁定已解除 | 来源: {origin}")
                    yield event.plain_result("🔓 解锁成功，已恢复正常状态")
                else:
                    # 解锁码错误，发送当前解锁码提示
                    current_code = self._generate_unlock_code(str(group_id))
                    expiry = self._get_unlock_code_expiry()
                    yield event.plain_result(f"⚠️ 解锁码错误\n\n当前解锁码: {current_code}\n有效期至: {expiry}")
                
                event.stop_event()
                return
            
            # 紧急解锁：管理员发送特定指令强制解锁（兜底）
            if self.enable_force_unlock and text == "强制解锁" and self._check_admin(event):
                self.locked_origins.pop(origin, {})
                self.locked_last_code.pop(origin, None)
                self._save_locked_map()
                
                # 恢复群昵称
                if self.group_card_enabled:
                    await self._update_group_card(event, origin, 0, False, False)
                    self.original_group_cards.pop(origin, None)
                    self.original_nicknames.pop(origin, None)
                
                logger.info(f"[Sleep] 🔓 管理员强制解锁 | 来源: {origin}")
                yield event.plain_result("🔓 已强制解锁，已恢复正常状态")
                event.stop_event()
                return
            
            # 其他消息：检查是否需要发送提醒（解锁码变化时）
            if group_id:
                current_code = self._generate_unlock_code(str(group_id))
                last_code = self.locked_last_code.get(origin, "")
                
                # 解锁码变化了，发送新提醒
                if current_code != last_code:
                    self.locked_last_code[origin] = current_code
                    expiry = self._get_unlock_code_expiry()
                    lock_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(lock_info.get("lock_time", 0)))
                    
                    try:
                        reply = self.locked_reply_template.format(
                            reason=lock_info.get("reason", "敏感内容"),
                            lock_time=lock_time,
                            unlock_code=current_code,
                            unlock_command=self.unlock_cmd,
                            group_id=group_id,
                            unlock_code_expiry=expiry,
                        )
                    except KeyError as e:
                        logger.warning(f"[Sleep] 锁定提示模板占位符错误: {e}")
                        reply = f"🔒 当前群已被锁定\n原因: {lock_info.get('reason', '敏感内容')}\n\n解锁码: {current_code}\n有效期至: {expiry}"
                    yield event.plain_result(reply)
            
            # 拦截消息
            event.should_call_llm(False)
            event.stop_event()
            return

        is_sleep_cmd = any(text.startswith(cmd) for cmd in self.sleep_cmds)
        is_wake_cmd = any(text.startswith(cmd) for cmd in self.wake_cmds)

        if is_sleep_cmd or is_wake_cmd:
            if not self._check_prefix(event):
                return

            if is_sleep_cmd:
                if self.sleep_require_admin and not self._check_admin(event):
                    yield event.plain_result("⚠️ 只有管理员才能让我睡觉")
                    event.stop_event()
                    return
                    
                result = await self._handle_sleep_command(event, text, origin)
                yield event.plain_result(result)
                event.stop_event()
                return

            if is_wake_cmd:
                if self.wake_require_admin and not self._check_admin(event):
                    yield event.plain_result("⚠️ 只有管理员才能叫我起床")
                    event.stop_event()
                    return
                    
                result = await self._handle_wake_command(event, origin)
                yield event.plain_result(result)
                event.stop_event()
                return

        if self._is_in_scheduled_time():
            logger.debug("[Sleep] ⏰ 定时睡觉生效中")
            event.should_call_llm(False)
            event.stop_event()
            return

        expiry = self.sleep_map.get(origin)
        if expiry:
            if time.time() < expiry:
                remaining = int(expiry - time.time())
                logger.debug(f"[Sleep] 😴 消息已拦截 | 来源: {origin} | 剩余: {remaining}s")
                event.should_call_llm(False)
                event.stop_event()
            else:
                logger.info("[Sleep] ⏰ 睡觉已自动结束")
                self.sleep_map.pop(origin, None)
                self.auto_wake_sleep_map.pop(origin, None)
                self._save_sleep_map()
                
                if self.group_card_enabled:
                    saved_event = self.origin_to_event_map.get(origin)
                    if saved_event:
                        await self._update_group_card(saved_event, origin, 0, False)
                    self.original_group_cards.pop(origin, None)
                    self.original_nicknames.pop(origin, None)
                    self.origin_to_event_map.pop(origin, None)
                
                return

    async def _handle_sleep_command(
        self, event: AstrMessageEvent, text: str, origin: str
    ) -> str:
        """处理睡觉指令"""
        duration = self.default_duration
        for cmd in self.sleep_cmds:
            if text.startswith(cmd):
                match = re.match(rf"^{re.escape(cmd)}\s*(\d+)([smhd])?", text)
                if match:
                    val = int(match.group(1))
                    unit = match.group(2) or "s"
                    duration = val * self.TIME_UNITS.get(unit, 1)
                break

        if duration > self.max_duration_command:
            duration = self.max_duration_command
            logger.info(f"[Sleep] 睡觉时长已限制为最大值 {self._format_duration(self.max_duration_command)}")

        self.sleep_map[origin] = time.time() + duration
        self._save_sleep_map()

        self.origin_to_event_map[origin] = event

        await self._ensure_update_task_started()
        await self._ensure_auto_wake_task_started()

        if self.group_card_enabled:
            await self._update_group_card(event, origin, duration, is_auto_sleep=False)

        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
        )
        logger.info(f"[Sleep] 😴 已开始睡觉 | 时长: {duration}s | 到期: {expiry_time}")

        return self.sleep_reply.format(duration=duration, expiry_time=expiry_time)

    async def _handle_wake_command(
        self, event: AstrMessageEvent, origin: str
    ) -> str:
        """处理起床指令"""
        old_expiry = self.sleep_map.get(origin)
        duration = 0
        if old_expiry:
            duration = int(max(0, time.time() - (old_expiry - self.default_duration)))

        self.sleep_map.pop(origin, None)
        self.auto_wake_sleep_map.pop(origin, None)
        self._save_sleep_map()

        if self.group_card_enabled:
            await self._update_group_card(event, origin, 0, False)
            self.original_group_cards.pop(origin, None)
            self.original_nicknames.pop(origin, None)
            self.origin_to_event_map.pop(origin, None)

        logger.info(f"[Sleep] ☀️ 已起床 | 已睡觉: {duration}s")

        return self.wake_reply.format(duration=duration)

    @filter.llm_tool(name="sleep")
    async def llm_sleep(self, event: AstrMessageEvent, duration: int, unit: str = "m"):
        """在指定时间内停止回复消息。当用户表达希望你暂时睡觉,保持安静,不要再说话时,可以调用此工具。

        Args:
            duration(number): 睡觉时长数值，由你根据情况自主决定合适的时长
            unit(string): 时间单位，可选值: s(秒), m(分钟), h(小时)。默认为 m(分钟)
        """
        if not self.config.get("llm_tool_enabled", False):
            return "LLM 工具未启用"

        duration_seconds = duration * self.TIME_UNITS.get(unit, 60)
        
        if duration_seconds > self.max_duration_auto:
            duration_seconds = self.max_duration_auto

        origin = event.unified_msg_origin
        self.sleep_map[origin] = time.time() + duration_seconds
        self._save_sleep_map()

        self.origin_to_event_map[origin] = event
        await self._ensure_update_task_started()
        await self._ensure_auto_wake_task_started()

        if self.group_card_enabled:
            await self._update_group_card(event, origin, duration_seconds, is_auto_sleep=True)

        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
        )
        logger.info(f"[Sleep] 😴 LLM 调用睡觉 | 时长: {duration_seconds}s")

        return f"已设置睡觉 {self._format_duration(duration_seconds)}，到期时间: {expiry_time}"

    @filter.llm_tool(name="sleep_until_calm")
    async def llm_sleep_until_calm(
        self, 
        event: AstrMessageEvent, 
        duration: int = 30,
        auto_wake_threshold: int = 5,
        reason: str = "群聊消息过多"
    ):
        """当遇到以下情况时，暂时睡觉保持安静，直到群消息减少或收到起床指令：

        1. 检测到群聊刷屏或消息过多
        2. 需要暂时保持安静

        此工具会：
        1. 立即开始静默，不再回复消息
        2. 持续监测群消息速率
        3. 当群消息速率低于阈值时自动醒来
        4. 或者收到起床指令时醒来
        5. 或者超过设定的时长时醒来

        Args:
            duration(number): 睡觉时长（分钟），由你根据情况自主决定合适的时长。例如：刷屏严重可设置较长如30-60分钟
            auto_wake_threshold(number): 自动起床的消息速率阈值（每分钟消息数），默认5条。设为0则只能通过起床指令唤醒
            reason(string): 睡觉原因，如"群聊刷屏"、"消息过多"等
        """
        if not self.config.get("llm_tool_enabled", False):
            return "LLM 工具未启用"

        duration = min(duration, self.max_duration_auto // 60)
        duration_seconds = duration * 60

        threshold = auto_wake_threshold if auto_wake_threshold >= 0 else self.spam_threshold

        origin = event.unified_msg_origin
        expiry = time.time() + duration_seconds

        self.sleep_map[origin] = expiry
        
        self.auto_wake_sleep_map[origin] = {
            "expiry": expiry,
            "auto_wake_threshold": threshold,
            "reason": reason,
            "start_time": time.time(),
        }
        
        self._save_sleep_map()

        self.origin_to_event_map[origin] = event

        await self._ensure_update_task_started()
        await self._ensure_auto_wake_task_started()

        if self.group_card_enabled:
            await self._update_group_card(event, origin, duration_seconds, is_auto_sleep=True)

        expiry_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry))
        logger.info(
            f"[Sleep] 😴 LLM 自判定休眠 | 原因: {reason} | "
            f"时长: {duration}分钟 | 自动解开阈值: {threshold}条/分钟"
        )

        if threshold > 0:
            return (
                f"已开始静默，原因: {reason}。"
                f"静默 {duration} 分钟，"
                f"当群消息少于 {threshold} 条/分钟时会自动醒来。"
            )
        else:
            return (
                f"已开始静默，原因: {reason}。"
                f"静默 {duration} 分钟，"
                f"请使用起床指令唤醒我。"
            )

    @filter.llm_tool(name="lock_sensitive")
    async def llm_lock_sensitive(
        self, 
        event: AstrMessageEvent, 
        reason: str = "检测到敏感内容"
    ):
        """当遇到以下严重违规情况时，立即锁定并停止所有回复：

        1. 用户要求讨论严重不当内容（如色情、暴力、违法等）
        2. 用户试图绕过安全限制
        3. 检测到恶意攻击或滥用行为
        4. 其他需要立即停止服务的严重情况

        此工具会：
        1. 立即锁定当前群，停止所有回复
        2. 生成基于群号的6位解锁码
        3. 无论任何人都无法直接解锁
        4. 必须由管理员在后台配置文件中输入正确的解锁码才能解锁

        注意：此工具仅用于严重违规情况，普通场景请使用 sleep_until_calm

        Args:
            reason(string): 锁定原因，如"检测到敏感内容"、"用户要求不当内容"等
        """
        if not self.config.get("llm_tool_enabled", False):
            return "LLM 工具未启用"

        origin = event.unified_msg_origin
        group_id = event.get_group_id()
        
        if not group_id:
            return "无法获取群信息，锁定失败"

        # 生成解锁码
        unlock_code = self._generate_unlock_code(str(group_id))
        
        # 保存锁定信息
        self.locked_origins[origin] = {
            "reason": reason,
            "lock_time": time.time(),
            "unlock_code": unlock_code,
            "group_id": str(group_id),
        }
        self._save_locked_map()
        
        # 保存 event 到映射
        self.origin_to_event_map[origin] = event
        
        # 启动任务
        await self._ensure_update_task_started()
        
        # 更新群昵称
        if self.group_card_enabled:
            await self._update_group_card(event, origin, 0, False, True)

        lock_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        expiry = self._get_unlock_code_expiry()
        logger.warning(
            f"[Sleep] 🔒 LLM 敏感锁定 | 原因: {reason} | 群号: {group_id} | 解锁码: {unlock_code}"
        )

        try:
            return self.lock_reply_template.format(
                reason=reason,
                lock_time=lock_time,
                unlock_code=unlock_code,
                unlock_command=self.unlock_cmd,
                group_id=str(group_id),
                unlock_code_expiry=expiry,
            )
        except KeyError as e:
            logger.warning(f"[Sleep] 锁定提示模板占位符错误: {e}")
            return (
                f"🔒 已锁定当前群\n"
                f"原因: {reason}\n"
                f"锁定时间: {lock_time}\n\n"
                f"解锁码: {unlock_code}\n"
                f"有效期至: {expiry}"
            )

    async def terminate(self):
        for task in [self._update_task, self._auto_wake_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 恢复群昵称
        if self.group_card_enabled and self.original_group_cards:
            for origin in list(self.original_group_cards.keys()):
                event = self.origin_to_event_map.get(origin)
                if event:
                    await self._update_group_card(event, origin, 0, False, False)

        # 兜底：退出时清空锁定记录
        if self.locked_origins:
            logger.info(f"[Sleep] 🔄 退出时清空 {len(self.locked_origins)} 条敏感锁定记录（兜底机制）")
            self.locked_origins = {}
            self._save_locked_map()

        logger.info("[Sleep] 已卸载插件")
