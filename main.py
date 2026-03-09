from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger, AstrBotConfig
import time
import re
import json
import asyncio
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
        self.require_prefix = config.get("require_prefix", False)
        
        # 分离的权限配置
        self.sleep_require_admin = config.get("sleep_require_admin", False)
        self.wake_require_admin = config.get("wake_require_admin", False)
        
        # 支持字符串配置，转换为列表
        if isinstance(self.sleep_cmds, str):
            self.sleep_cmds = re.split(r"[\s,]+", self.sleep_cmds)
        if isinstance(self.wake_cmds, str):
            self.wake_cmds = re.split(r"[\s,]+", self.wake_cmds)

        # 时长配置
        # 默认睡觉时长
        self.default_duration = self._get_duration_config("default_duration", 600, 60, 86400)
        
        # 指令触发最大时长（默认12小时）
        self.max_duration_command = self._get_duration_config("max_duration_command", 43200, 60, 86400)
        
        # 自判定休眠最大时长（默认3小时）
        self.max_duration_auto = self._get_duration_config("max_duration_auto", 10800, 60, 86400)

        self.sleep_reply = config.get("sleep_reply", "好的，我去睡觉了~💤")
        self.wake_reply = config.get("wake_reply", "早安~我醒来了☀️")

        # 群昵称更新配置
        self.group_card_enabled = config.get("group_card_update_enabled", False)
        self.group_card_template = config.get(
            "group_card_template", "{original_name}[睡觉中 {remaining}]"
        )
        # 自判定休眠的群昵称模板
        self.group_card_template_auto = config.get(
            "group_card_template_auto", "{original_name}[静默中 {remaining}]"
        )
        self.original_group_cards = {}
        self.original_nicknames = {}
        self.origin_to_event_map = {}
        self._update_task = None

        # 定时睡觉配置
        self.scheduled_enabled = config.get("scheduled_sleep_enabled", False)
        self.scheduled_times_text = config.get("scheduled_sleep_times", "23:00-07:00")
        self.scheduled_time_ranges = self._parse_time_ranges(self.scheduled_times_text)

        # 刷屏检测配置（可配置）
        self.spam_detect_enabled = config.get("spam_detect_enabled", False)
        self.spam_threshold = config.get("spam_threshold", 10)  # 消息数阈值
        self.spam_window = config.get("spam_window", 60)  # 检测窗口（秒）
        self.spam_auto_sleep_duration = config.get("spam_auto_sleep_duration", 1800)  # 刷屏自动睡觉时长（秒）
        
        # 群消息计数器
        self.message_counters: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 自动解开的睡觉记录
        self.auto_wake_sleep_map: dict[str, dict] = {}

        self.sleep_map = {}
        self.data_dir = (
            Path(__file__).parent.parent.parent
            / "plugin_data"
            / "astrbot_plugin_sleep"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_map_path = self.data_dir / "sleep_map.json"
        self._load_sleep_map()

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
            logger.info(f"[Sleep] 群昵称更新已启用 | 普通模板: {self.group_card_template} | 自动模板: {self.group_card_template_auto}")

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
        """格式化剩余时间显示
        
        大于1小时显示为 X.X小时
        小于1小时显示为 X分钟
        """
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
                    
                # 兼容旧格式
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
        self, event: AstrMessageEvent, origin: str, remaining_seconds: int, is_auto_sleep: bool = False
    ) -> None:
        """更新群昵称显示剩余时长
        
        Args:
            event: 消息事件
            origin: 消息来源
            remaining_seconds: 剩余秒数
            is_auto_sleep: 是否是自判定休眠
        """
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

            if remaining_seconds > 0:
                original_card = self.original_group_cards.get(origin, "")
                original_nickname = self.original_nicknames.get(origin, "")
                original_name = original_card if original_card else original_nickname
                
                # 格式化剩余时间
                remaining_str = self._format_remaining_time(remaining_seconds)
                
                # 根据是否是自判定休眠选择模板
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

                if not self.sleep_map:
                    continue

                current_time = time.time()
                for origin, expiry in list(self.sleep_map.items()):
                    remaining_seconds = int(expiry - current_time)
                    if remaining_seconds > 0:
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            # 检查是否是自判定休眠
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

        # 指令触发最大时长限制
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
        
        # 限制为自判定休眠最大时长
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
        2. 用户要求讨论不适当内容（如色情、暴力、违法等）
        3. 需要拒绝回答敏感问题
        4. 其他需要暂时保持安静的情况

        此工具会：
        1. 立即开始静默，不再回复消息
        2. 持续监测群消息速率
        3. 当群消息速率低于阈值时自动醒来
        4. 或者收到起床指令时醒来
        5. 或者超过设定的时长时醒来

        Args:
            duration(number): 睡觉时长（分钟），由你根据情况自主决定合适的时长。例如：刷屏严重可设置较长如30-60分钟，拒绝敏感内容可设置较短如5-15分钟
            auto_wake_threshold(number): 自动起床的消息速率阈值（每分钟消息数），默认5条。设为0则只能通过起床指令唤醒
            reason(string): 睡觉原因，如"群聊刷屏"、"拒绝回答敏感内容"、"内容不适当"等
        """
        if not self.config.get("llm_tool_enabled", False):
            return "LLM 工具未启用"

        # 限制为自判定休眠最大时长
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

        # 使用自判定休眠的群昵称模板
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

    async def terminate(self):
        for task in [self._update_task, self._auto_wake_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self.group_card_enabled and self.original_group_cards:
            for origin in list(self.original_group_cards.keys()):
                event = self.origin_to_event_map.get(origin)
                if event:
                    await self._update_group_card(event, origin, 0, False)

        logger.info("[Sleep] 已卸载插件")
