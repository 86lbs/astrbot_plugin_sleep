"""
AstrBot 睡觉插件 - 让 bot 暂时保持安静

功能特性：
- 手动睡觉/起床指令
- 定时睡觉
- LLM 工具调用
- 群昵称状态显示
- 管理员权限控制
- 刷屏检测自动睡觉

作者: 86lbs
版本: v1.3.0
"""

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
from typing import Optional, Union


class SleepPlugin(Star):
    """睡觉插件 - 让 bot 暂时保持安静
    
    该插件提供了让 bot 在指定时间内保持沉默的功能，支持：
    - 指令触发睡觉/起床
    - LLM 工具调用触发睡觉
    - 定时睡觉
    - 群昵称状态显示
    - 刷屏检测自动睡觉
    """
    
    # 时间单位转换常量（秒）
    TIME_UNITS = {
        "s": 1,      # 秒
        "m": 60,     # 分钟
        "h": 3600,   # 小时
        "d": 86400   # 天
    }
    
    # 有效的单位列表
    VALID_UNITS = list(TIME_UNITS.keys())
    
    # 时长限制常量
    MAX_COMMAND_DURATION = 43200    # 指令触发最大时长：12小时
    MAX_LLM_DURATION = 3600         # LLM 工具最大时长：1小时
    MAX_AUTO_SLEEP_DURATION = 10800 # 自判定休眠最大时长：3小时

    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化睡觉插件
        
        Args:
            context: AstrBot 插件上下文
            config: 插件配置对象
        """
        super().__init__(context)
        self.config = config
        
        # 初始化基础配置
        self._init_basic_config()
        
        # 初始化权限配置
        self._init_permission_config()
        
        # 初始化时长配置
        self._init_duration_config()
        
        # 初始化回复消息配置
        self._init_reply_config()
        
        # 初始化群昵称更新配置
        self._init_group_card_config()
        
        # 初始化定时睡觉配置
        self._init_scheduled_config()
        
        # 初始化刷屏检测配置
        self._init_spam_detect_config()
        
        # 初始化数据存储
        self._init_data_storage()
        
        # 初始化后台任务
        self._init_background_tasks()
        
        # 输出加载日志
        self._log_init_info()

    def _init_basic_config(self) -> None:
        """初始化基础配置"""
        # 从配置读取优先级
        self.plugin_priority = self.config.get("priority", 10000)
        
        # 获取唤醒前缀
        self.wake_prefix: list[str] = self.context.get_config().get("wake_prefix", [])
        
        # 获取指令列表（支持字符串配置转换为列表）
        self.sleep_cmds = self._parse_command_config(
            self.config.get("sleep_commands", ["睡觉", "sleep"])
        )
        self.wake_cmds = self._parse_command_config(
            self.config.get("wake_commands", ["起床", "醒来", "wake"])
        )
        
        # 是否需要前缀
        self.require_prefix = self.config.get("require_prefix", False)

    def _init_permission_config(self) -> None:
        """初始化权限配置"""
        self.sleep_require_admin = self.config.get("sleep_require_admin", False)
        self.wake_require_admin = self.config.get("wake_require_admin", False)

    def _init_duration_config(self) -> None:
        """初始化时长配置，包含范围验证"""
        duration_config = self.config.get("default_duration", 600)
        
        # 验证时长配置的有效性
        if not isinstance(duration_config, (int, float)) or not (0 <= duration_config <= 43200):
            logger.warning(
                f"[Sleep] ⚠️ default_duration 配置无效({duration_config})，使用默认值 600s"
            )
            self.default_duration = 600
            # 尝试修正配置
            try:
                self.config["default_duration"] = 600
                self.config.save_config()
            except Exception as e:
                logger.debug(f"[Sleep] 保存配置失败: {e}")
        else:
            self.default_duration = int(duration_config)

    def _init_reply_config(self) -> None:
        """初始化回复消息配置"""
        self.sleep_reply = self.config.get("sleep_reply", "好的，我去睡觉了~💤")
        self.wake_reply = self.config.get("wake_reply", "早安~我醒来了☀️")

    def _init_group_card_config(self) -> None:
        """初始化群昵称更新配置"""
        self.group_card_enabled = self.config.get("group_card_update_enabled", False)
        self.group_card_template = self.config.get(
            "group_card_template", "{original_name}[睡觉中 {remaining}]"
        )
        self.group_card_template_auto = self.config.get(
            "group_card_template_auto", "{original_name}[静默中 {remaining}]"
        )
        
        # 存储原始群昵称和昵称
        self.original_group_cards: dict[str, str] = {}
        self.original_nicknames: dict[str, str] = {}
        self.origin_to_event_map: dict[str, AstrMessageEvent] = {}

    def _init_scheduled_config(self) -> None:
        """初始化定时睡觉配置"""
        self.scheduled_enabled = self.config.get("scheduled_sleep_enabled", False)
        self.scheduled_times_text = self.config.get("scheduled_sleep_times", "23:00-07:00")
        self.scheduled_time_ranges = self._parse_time_ranges(self.scheduled_times_text)

    def _init_spam_detect_config(self) -> None:
        """初始化刷屏检测配置"""
        self.spam_detect_enabled = self.config.get("spam_detect_enabled", False)
        self.spam_threshold = self.config.get("spam_threshold", 10)
        self.spam_window = self.config.get("spam_window", 60)
        
        # 群消息计数器（使用 deque 限制大小，提高内存效率）
        self.message_counters: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        
        # 自动解开的睡觉记录
        self.auto_wake_sleep_map: dict[str, dict] = {}

    def _init_data_storage(self) -> None:
        """初始化数据存储"""
        self.sleep_map: dict[str, float] = {}
        
        # 设置数据目录
        self.data_dir = (
            Path(__file__).parent.parent.parent
            / "plugin_data"
            / "astrbot_plugin_sleep"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_map_path = self.data_dir / "sleep_map.json"
        
        # 加载持久化的睡觉记录
        self._load_sleep_map()

    def _init_background_tasks(self) -> None:
        """初始化后台任务状态"""
        self._update_task: Optional[asyncio.Task] = None
        self._update_task_started = False
        self._auto_wake_task: Optional[asyncio.Task] = None
        self._auto_wake_task_started = False

    def _parse_command_config(self, config_value: Union[str, list]) -> list[str]:
        """解析指令配置，支持字符串和列表格式
        
        Args:
            config_value: 配置值，可以是字符串或列表
            
        Returns:
            解析后的指令列表
        """
        if isinstance(config_value, str):
            # 支持逗号或空格分隔的字符串
            return [cmd.strip() for cmd in re.split(r"[\s,]+", config_value) if cmd.strip()]
        return list(config_value)

    def _log_init_info(self) -> None:
        """输出插件加载日志"""
        log_parts = [
            f"指令: {self.sleep_cmds} & {self.wake_cmds}",
            f"默认时长: {self.default_duration}s",
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
            log_parts.append(f"刷屏检测: 阈值{self.spam_threshold}条/{self.spam_window}s")
            
        logger.info(f"[Sleep] 已加载 | " + " | ".join(log_parts))

        if self.group_card_enabled:
            logger.info(
                f"[Sleep] 群昵称更新已启用 | "
                f"普通模板: {self.group_card_template} | "
                f"自动模板: {self.group_card_template_auto}"
            )

    def _format_remaining_time(self, seconds: int) -> str:
        """格式化剩余时间显示
        
        大于1小时显示为 X.X小时
        小于1小时显示为 X分钟
        
        Args:
            seconds: 剩余秒数
            
        Returns:
            格式化后的时间字符串
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
        """解析时间范围文本
        
        Args:
            time_text: 时间范围文本，每行一个时间段
            
        Returns:
            解析后的时间范围列表，每个元素为 (开始时间, 结束时间)
        """
        time_ranges = []

        for line in time_text.strip().split("\n"):
            line = line.strip()
            # 跳过空行和注释行
            if not line or line.startswith("#"):
                continue

            # 使用正则匹配时间范围格式
            match = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", line)
            if not match:
                logger.warning(f"[Sleep] ⚠️ 无法解析时间范围: {line}")
                continue

            start_time, end_time = match.groups()
            try:
                # 验证时间格式
                datetime.strptime(start_time, "%H:%M")
                datetime.strptime(end_time, "%H:%M")
                time_ranges.append((start_time, end_time))
            except ValueError:
                logger.warning(f"[Sleep] ⚠️ 无效的时间格式: {line}")

        if not time_ranges and self.scheduled_enabled:
            logger.warning("[Sleep] ⚠️ 未配置有效的定时时间段，定时睡觉将不会生效")

        return time_ranges

    def _load_sleep_map(self) -> None:
        """从文件加载睡觉记录"""
        try:
            if self.sleep_map_path.exists():
                with open(self.sleep_map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # 兼容旧格式数据
                if isinstance(data, dict):
                    if all(isinstance(v, (int, float)) for v in data.values()):
                        # 简单格式：{origin: expiry}
                        self.sleep_map = {k: float(v) for k, v in data.items()}
                    else:
                        # 复杂格式：可能包含自动解开配置
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

    def _save_sleep_map(self) -> None:
        """保存睡觉记录到文件"""
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
        """检查当前时间是否在定时睡觉时间段内
        
        Returns:
            如果在定时睡觉时间段内返回 True，否则返回 False
        """
        if not self.scheduled_enabled or not self.scheduled_time_ranges:
            return False

        current_minutes = datetime.now().hour * 60 + datetime.now().minute

        for start_time_str, end_time_str in self.scheduled_time_ranges:
            start_h, start_m = map(int, start_time_str.split(":"))
            end_h, end_m = map(int, end_time_str.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            # 处理跨天情况（如 23:00-07:00）
            if start_minutes <= end_minutes:
                # 不跨天
                in_range = start_minutes <= current_minutes <= end_minutes
            else:
                # 跨天
                in_range = current_minutes >= start_minutes or current_minutes < end_minutes
                
            if in_range:
                return True

        return False

    def _check_prefix(self, event: AstrMessageEvent) -> bool:
        """检查消息是否满足前缀要求
        
        Args:
            event: 消息事件对象
            
        Returns:
            如果满足前缀要求返回 True，否则返回 False
        """
        if not self.require_prefix:
            return True

        chain = event.get_messages()
        if not chain:
            return False

        first_seg = chain[0]
        if isinstance(first_seg, Comp.Plain):
            # 检查文本是否以任意唤醒前缀开头
            return any(first_seg.text.startswith(prefix) for prefix in self.wake_prefix)
        elif isinstance(first_seg, Comp.At):
            # @ 机器人也算作满足前缀
            return str(first_seg.qq) == str(event.get_self_id())
        else:
            return False

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否是管理员
        
        Args:
            event: 消息事件对象
            
        Returns:
            如果是管理员返回 True，否则返回 False
        """
        try:
            astrbot_config = self.context.get_config()
            admins = []
            
            # 兼容不同类型的配置对象
            if hasattr(astrbot_config, 'get'):
                admins = astrbot_config.get("admins_id", [])
            elif isinstance(astrbot_config, dict):
                admins = astrbot_config.get("admins_id", [])
            
            sender_id = event.get_sender_id()
            # 统一转换为字符串进行比较
            is_admin = str(sender_id) in [str(admin) for admin in admins]
            
            return is_admin
        except Exception as e:
            logger.error(f"[Sleep] 检查管理员权限时出错: {e}")
            return False

    def _update_message_counter(self, origin: str) -> int:
        """更新消息计数器，返回当前窗口内的消息数
        
        Args:
            origin: 消息来源标识
            
        Returns:
            当前时间窗口内的消息数量
        """
        now = time.time()
        counter = self.message_counters[origin]
        
        # 移除过期的记录
        while counter and counter[0] < now - self.spam_window:
            counter.popleft()
        
        # 添加新记录
        counter.append(now)
        
        return len(counter)

    def _get_message_rate(self, origin: str) -> int:
        """获取当前窗口内的消息数（不更新计数器）
        
        Args:
            origin: 消息来源标识
            
        Returns:
            当前时间窗口内的消息数量
        """
        now = time.time()
        counter = self.message_counters[origin]
        
        # 只移除过期记录，不添加新记录
        while counter and counter[0] < now - self.spam_window:
            counter.popleft()
        
        return len(counter)

    async def _update_group_card(
        self, 
        event: AstrMessageEvent, 
        origin: str, 
        remaining_seconds: int, 
        is_auto_sleep: bool = False
    ) -> None:
        """更新群昵称显示剩余时长
        
        Args:
            event: 消息事件对象
            origin: 消息来源标识
            remaining_seconds: 剩余秒数
            is_auto_sleep: 是否是自判定休眠（刷屏检测触发）
        """
        if not self.group_card_enabled:
            return

        try:
            # 延迟导入，避免在非 QQ 平台报错
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
            # 获取原始群昵称（仅在首次获取）
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

            # 构建新的群昵称
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
                # 恢复原始群昵称
                card = self.original_group_cards.get(origin, "")

            # 设置群昵称（限制长度为60字符）
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
                            is_auto = origin in self.auto_wake_sleep_map
                            await self._update_group_card(event, origin, remaining_seconds, is_auto)
                    else:
                        # 睡觉时间已到，清理状态
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            await self._update_group_card(event, origin, 0, False)
                        
                        # 清理相关数据
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
                    
                    # 检查是否超时
                    if current_time >= expiry:
                        await self._auto_wake(origin, "睡觉时间已到")
                        continue

                    # 检查消息速率是否低于阈值
                    threshold = config.get("auto_wake_threshold", 0)
                    if threshold > 0:
                        rate = self._get_message_rate(origin)
                        if rate < threshold:
                            await self._auto_wake(
                                origin, 
                                f"群消息速率已降至 {rate} 条/{self.spam_window}s"
                            )

        except asyncio.CancelledError:
            logger.info("[Sleep] 自动解开检测任务已停止")
        except Exception as e:
            logger.error(f"[Sleep] 自动解开检测任务异常: {e}")

    async def _auto_wake(self, origin: str, reason: str) -> None:
        """自动解开睡觉状态
        
        Args:
            origin: 消息来源标识
            reason: 自动解开的原因
        """
        if origin not in self.sleep_map:
            return
            
        config = self.auto_wake_sleep_map.get(origin, {})
        
        # 清理睡觉状态
        self.sleep_map.pop(origin, None)
        self.auto_wake_sleep_map.pop(origin, None)
        self._save_sleep_map()

        # 恢复群昵称
        if self.group_card_enabled:
            event = self.origin_to_event_map.get(origin)
            if event:
                await self._update_group_card(event, origin, 0, False)
            self.original_group_cards.pop(origin, None)
            self.original_nicknames.pop(origin, None)
            self.origin_to_event_map.pop(origin, None)

        logger.info(f"[Sleep] 🌅 自动起床 | 来源: {origin} | 原因: {reason}")
        
        # 发送自动起床通知
        try:
            event = self.origin_to_event_map.get(origin)
            if event:
                from astrbot.api.event import MessageChain
                chain = MessageChain().message(f"🌅 {reason}，我醒来了~")
                await self.context.send_message(origin, chain)
        except Exception as e:
            logger.debug(f"[Sleep] 发送自动起床通知失败: {e}")

    def _is_llm_tool_enabled(self) -> bool:
        """检查 LLM 工具是否启用
        
        Returns:
            如果启用返回 True，否则返回 False
        """
        return self.config.get("llm_tool_enabled", True)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def handle_message(self, event: AstrMessageEvent):
        """处理消息事件的主入口
        
        Args:
            event: 消息事件对象
        """
        text = event.get_message_str().strip()
        origin = event.unified_msg_origin

        # 更新消息计数器（用于刷屏检测）
        if self.spam_detect_enabled:
            self._update_message_counter(origin)

        # 检查是否是睡觉或起床指令
        is_sleep_cmd = any(text.startswith(cmd) for cmd in self.sleep_cmds)
        is_wake_cmd = any(text.startswith(cmd) for cmd in self.wake_cmds)

        if is_sleep_cmd or is_wake_cmd:
            # 检查前缀要求
            if not self._check_prefix(event):
                return

            if is_sleep_cmd:
                # 检查睡觉权限
                if self.sleep_require_admin and not self._check_admin(event):
                    yield event.plain_result("⚠️ 只有管理员才能让我睡觉")
                    event.stop_event()
                    return
                    
                result = await self._handle_sleep_command(event, text, origin)
                yield event.plain_result(result)
                event.stop_event()
                return

            if is_wake_cmd:
                # 检查起床权限
                if self.wake_require_admin and not self._check_admin(event):
                    yield event.plain_result("⚠️ 只有管理员才能叫我起床")
                    event.stop_event()
                    return
                    
                result = await self._handle_wake_command(event, origin)
                yield event.plain_result(result)
                event.stop_event()
                return

        # 检查是否在定时睡觉时间段内
        if self._is_in_scheduled_time():
            logger.debug("[Sleep] ⏰ 定时睡觉生效中")
            event.should_call_llm(False)
            event.stop_event()
            return

        # 检查是否在睡觉状态
        expiry = self.sleep_map.get(origin)
        if expiry:
            if time.time() < expiry:
                remaining = int(expiry - time.time())
                logger.debug(f"[Sleep] 😴 消息已拦截 | 来源: {origin} | 剩余: {remaining}s")
                event.should_call_llm(False)
                event.stop_event()
            else:
                # 睡觉时间已到，自动结束
                logger.info("[Sleep] ⏰ 睡觉已自动结束")
                self.sleep_map.pop(origin, None)
                self.auto_wake_sleep_map.pop(origin, None)
                self._save_sleep_map()
                
                # 恢复群昵称
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
        """处理睡觉指令
        
        Args:
            event: 消息事件对象
            text: 消息文本
            origin: 消息来源标识
            
        Returns:
            回复消息
        """
        # 解析时长参数
        duration = self.default_duration
        for cmd in self.sleep_cmds:
            if text.startswith(cmd):
                # 匹配 "睡觉 10m" 或 "睡觉 10" 格式
                match = re.match(rf"^{re.escape(cmd)}\s*(\d+)([smhd])?", text)
                if match:
                    val = int(match.group(1))
                    unit = match.group(2) or "s"
                    duration = val * self.TIME_UNITS.get(unit, 1)
                break

        # 限制最大时长
        if duration > self.MAX_COMMAND_DURATION:
            duration = self.MAX_COMMAND_DURATION
            logger.info(f"[Sleep] 睡觉时长已限制为最大值 12 小时")

        # 设置睡觉状态
        self.sleep_map[origin] = time.time() + duration
        self._save_sleep_map()

        # 保存事件对象用于后续群昵称更新
        self.origin_to_event_map[origin] = event

        # 启动后台任务
        await self._ensure_update_task_started()
        await self._ensure_auto_wake_task_started()

        # 更新群昵称
        if self.group_card_enabled:
            await self._update_group_card(event, origin, duration, is_auto_sleep=False)

        # 计算到期时间
        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
        )
        logger.info(f"[Sleep] 😴 已开始睡觉 | 时长: {duration}s | 到期: {expiry_time}")

        return self.sleep_reply.format(duration=duration, expiry_time=expiry_time)

    async def _handle_wake_command(
        self, event: AstrMessageEvent, origin: str
    ) -> str:
        """处理起床指令
        
        Args:
            event: 消息事件对象
            origin: 消息来源标识
            
        Returns:
            回复消息
        """
        old_expiry = self.sleep_map.get(origin)
        duration = 0
        if old_expiry:
            duration = int(max(0, time.time() - (old_expiry - self.default_duration)))

        # 清理睡觉状态
        self.sleep_map.pop(origin, None)
        self.auto_wake_sleep_map.pop(origin, None)
        self._save_sleep_map()

        # 恢复群昵称
        if self.group_card_enabled:
            await self._update_group_card(event, origin, 0, False)
            self.original_group_cards.pop(origin, None)
            self.original_nicknames.pop(origin, None)
            self.origin_to_event_map.pop(origin, None)

        logger.info(f"[Sleep] ☀️ 已起床 | 已睡觉: {duration}s")

        return self.wake_reply.format(duration=duration)

    @filter.llm_tool(name="sleep")
    async def llm_sleep(self, event: AstrMessageEvent, duration: int, unit: str = "m") -> str:
        """在指定时间内停止回复消息。当用户表达希望你暂时睡觉,保持安静,不要再说话时,可以调用此工具。

        Args:
            duration(number): 睡觉时长数值，最长不超过 60 分钟
            unit(string): 时间单位，可选值: s(秒), m(分钟), h(小时)。默认为 m(分钟)
        """
        # 检查 LLM 工具是否启用
        if not self._is_llm_tool_enabled():
            return "LLM 工具未启用，请在插件配置中开启 llm_tool_enabled 选项。"

        try:
            # 参数类型转换和验证
            duration = int(duration)
            unit = str(unit).lower()
            
            # 验证单位有效性
            if unit not in self.VALID_UNITS:
                logger.warning(f"[Sleep] LLM 传入了无效的单位 '{unit}'，使用默认单位 'm'")
                unit = "m"
            
            # 计算实际时长（秒）
            duration_seconds = duration * self.TIME_UNITS.get(unit, 60)
            
            # 限制最大时长为1小时
            if duration_seconds > self.MAX_LLM_DURATION:
                duration_seconds = self.MAX_LLM_DURATION
                logger.info(f"[Sleep] LLM 睡觉时长已限制为最大值 1 小时")

            origin = event.unified_msg_origin
            self.sleep_map[origin] = time.time() + duration_seconds
            self._save_sleep_map()

            # 保存事件对象
            self.origin_to_event_map[origin] = event
            
            # 启动后台任务
            await self._ensure_update_task_started()
            await self._ensure_auto_wake_task_started()

            # 更新群昵称
            if self.group_card_enabled:
                await self._update_group_card(event, origin, duration_seconds, is_auto_sleep=False)

            # 计算到期时间
            expiry_time = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
            )
            logger.info(f"[Sleep] 😴 LLM 调用睡觉 | 时长: {duration_seconds}s")

            return f"已设置睡觉 {int(duration_seconds/60)} 分钟，到期时间: {expiry_time}"
            
        except (ValueError, TypeError) as e:
            error_msg = f"参数错误: {e}"
            logger.error(f"[Sleep] LLM sleep 工具参数错误: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"设置睡觉失败: {e}"
            logger.error(f"[Sleep] LLM sleep 工具执行失败: {e}")
            return error_msg

    @filter.llm_tool(name="sleep_until_calm")
    async def llm_sleep_until_calm(
        self, 
        event: AstrMessageEvent, 
        max_duration: int = 30,
        auto_wake_threshold: int = 5,
        reason: str = "群聊消息过多"
    ) -> str:
        """当检测到群聊刷屏或消息过多时，暂时睡觉保持安静，直到群消息减少或收到起床指令。

        此工具会：
        1. 立即开始睡觉，不再回复消息
        2. 持续监测群消息速率
        3. 当群消息速率低于阈值时自动起床
        4. 或者收到起床指令时起床
        5. 或者超过最大时长时起床

        Args:
            max_duration(number): 最大睡觉时长（分钟），默认30分钟，最长3小时
            auto_wake_threshold(number): 自动起床的消息速率阈值（每分钟消息数），默认5条
            reason(string): 睡觉原因，如"群聊刷屏"、"消息过多"等
        """
        # 检查 LLM 工具是否启用
        if not self._is_llm_tool_enabled():
            return "LLM 工具未启用，请在插件配置中开启 llm_tool_enabled 选项。"

        try:
            # 参数类型转换和验证
            max_duration = int(max_duration)
            auto_wake_threshold = int(auto_wake_threshold)
            reason = str(reason)
            
            # 限制最大时长为3小时
            max_duration = min(max_duration, self.MAX_AUTO_SLEEP_DURATION // 60)
            duration_seconds = max_duration * 60

            # 获取阈值，如果传入0则使用默认配置
            threshold = auto_wake_threshold if auto_wake_threshold > 0 else self.spam_threshold

            origin = event.unified_msg_origin
            expiry = time.time() + duration_seconds

            # 设置睡觉状态
            self.sleep_map[origin] = expiry
            
            # 设置自动解开配置
            self.auto_wake_sleep_map[origin] = {
                "expiry": expiry,
                "auto_wake_threshold": threshold,
                "reason": reason,
                "start_time": time.time(),
            }
            
            self._save_sleep_map()

            # 保存事件对象
            self.origin_to_event_map[origin] = event

            # 启动后台任务
            await self._ensure_update_task_started()
            await self._ensure_auto_wake_task_started()

            # 更新群昵称（使用自判定休眠模板）
            if self.group_card_enabled:
                await self._update_group_card(event, origin, duration_seconds, is_auto_sleep=True)

            # 计算到期时间
            expiry_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry))
            logger.info(
                f"[Sleep] 😴 LLM 刷屏检测睡觉 | 原因: {reason} | "
                f"最大时长: {max_duration}分钟 | 自动解开阈值: {threshold}条/分钟"
            )

            return (
                f"已开始静默，原因: {reason}。"
                f"最长静默 {max_duration} 分钟，"
                f"当群消息少于 {threshold} 条/分钟时会自动醒来。"
            )
            
        except (ValueError, TypeError) as e:
            error_msg = f"参数错误: {e}"
            logger.error(f"[Sleep] LLM sleep_until_calm 工具参数错误: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"设置静默失败: {e}"
            logger.error(f"[Sleep] LLM sleep_until_calm 工具执行失败: {e}")
            return error_msg

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 取消后台任务
        for task in [self._update_task, self._auto_wake_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 恢复所有群昵称
        if self.group_card_enabled and self.original_group_cards:
            for origin in list(self.original_group_cards.keys()):
                event = self.origin_to_event_map.get(origin)
                if event:
                    await self._update_group_card(event, origin, 0, False)

        logger.info("[Sleep] 已卸载插件")
