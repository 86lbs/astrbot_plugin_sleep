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
        self.require_admin = config.get("require_admin", False)
        # 支持字符串配置，转换为列表
        if isinstance(self.sleep_cmds, str):
            self.sleep_cmds = re.split(r"[\s,]+", self.sleep_cmds)
        if isinstance(self.wake_cmds, str):
            self.wake_cmds = re.split(r"[\s,]+", self.wake_cmds)

        # 限制 default_duration 范围在 0-86400 秒(0-24小时)
        duration_config = config.get("default_duration", 600)
        if not isinstance(duration_config, (int, float)) or not (
            0 <= duration_config <= 86400
        ):
            logger.warning(
                f"[Sleep] ⚠️ default_duration 配置无效({duration_config})，使用默认值 600s"
            )
            self.default_duration = 600
            # 更新配置文件中的值为默认值
            config["default_duration"] = 600
            config.save_config()
        else:
            self.default_duration = int(duration_config)

        self.sleep_reply = config.get("sleep_reply", "好的，我去睡觉了~💤")
        self.wake_reply = config.get("wake_reply", "早安~我醒来了☀️")

        # 群昵称更新配置
        self.group_card_enabled = config.get("group_card_update_enabled", False)
        self.group_card_template = config.get(
            "group_card_template", "{original_name}[睡觉中 {remaining}分钟]"
        )
        self.original_group_cards = {}  # 存储原始群昵称
        self.original_nicknames = {}  # 存储原始QQ昵称
        self.origin_to_event_map = {}  # 存储 origin 到 event 的映射
        self._update_task = None  # 定时更新任务

        # 定时睡觉配置
        self.scheduled_enabled = config.get("scheduled_sleep_enabled", False)
        self.scheduled_times_text = config.get("scheduled_sleep_times", "23:00-07:00")
        self.scheduled_time_ranges = self._parse_time_ranges(self.scheduled_times_text)

        self.sleep_map = {}
        # 使用 pathlib 优化路径处理
        self.data_dir = (
            Path(__file__).parent.parent.parent
            / "plugin_data"
            / "astrbot_plugin_sleep"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_map_path = self.data_dir / "sleep_map.json"
        self._load_sleep_map()

        # 群昵称更新任务(延迟启动)
        self._update_task = None
        self._update_task_started = False

        if self.scheduled_enabled:
            time_ranges_str = ", ".join(
                [f"{start}-{end}" for start, end in self.scheduled_time_ranges]
            )
            logger.info(
                f"[Sleep] 已加载 | 指令: {self.sleep_cmds} & {self.wake_cmds} | 默认时长: {self.default_duration}s | 优先级: {self.plugin_priority} | 定时: {time_ranges_str}"
            )
        else:
            logger.info(
                f"[Sleep] 已加载 | 指令: {self.sleep_cmds} & {self.wake_cmds} | 默认时长: {self.default_duration}s | 优先级: {self.plugin_priority}"
            )

        if self.group_card_enabled:
            logger.info(f"[Sleep] 群昵称更新已启用 | 模板: {self.group_card_template}")

    def _parse_time_ranges(self, time_text: str) -> list[tuple[str, str]]:
        """解析时间范围文本

        Args:
            time_text: 时间范围文本，每行一个，格式: HH:MM-HH:MM

        Returns:
            list[tuple[str, str]]: 时间范围列表，每个元素是 (开始时间, 结束时间)
        """
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
                    self.sleep_map = json.load(f)

                self.sleep_map = {k: float(v) for k, v in self.sleep_map.items()}
                if self.sleep_map:
                    logger.info(f"[Sleep] 加载了 {len(self.sleep_map)} 条睡觉记录")
        except Exception as e:
            logger.warning(f"[Sleep] ⚠️ 加载睡觉记录失败: {e}")

    def _save_sleep_map(self):
        try:
            with open(self.sleep_map_path, "w", encoding="utf-8") as f:
                json.dump(self.sleep_map, f)
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

            # 跨天：23:00-07:00 或 不跨天：08:00-18:00
            in_range = (
                start_minutes <= current_minutes <= end_minutes
                if start_minutes <= end_minutes
                else current_minutes >= start_minutes or current_minutes < end_minutes
            )
            if in_range:
                return True

        return False

    def _check_prefix(self, event: AstrMessageEvent) -> bool:
        """检查消息是否满足前缀要求

        Returns:
            bool: True 表示满足前缀要求(或不需要前缀)，False 表示不满足前缀要求
        """
        if not self.require_prefix:
            return True

        chain = event.get_messages()
        if not chain:
            return False

        first_seg = chain[0]
        # 前缀触发
        if isinstance(first_seg, Comp.Plain):
            return any(first_seg.text.startswith(prefix) for prefix in self.wake_prefix)
        # @bot触发
        elif isinstance(first_seg, Comp.At):
            return str(first_seg.qq) == str(event.get_self_id())
        else:
            return False

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否是管理员

        Returns:
            bool: True 表示是管理员(或不需要管理员权限)，False 表示不是管理员
        """
        if not self.require_admin:
            return True

        # 获取管理员列表 - 根据 AstrBot 官方源码，字段名是 admins_id
        try:
            # 从 context 获取 AstrBot 配置
            astrbot_config = self.context.get_config()
            
            # 根据官方源码 default.py，管理员字段名是 admins_id
            admins = []
            if hasattr(astrbot_config, 'get'):
                admins = astrbot_config.get("admins_id", [])
            elif isinstance(astrbot_config, dict):
                admins = astrbot_config.get("admins_id", [])
            
            sender_id = event.get_sender_id()
            
            # 检查发送者是否在管理员列表中
            is_admin = str(sender_id) in [str(admin) for admin in admins]
            
            if not is_admin:
                logger.debug(f"[Sleep] 用户 {sender_id} 不在管理员列表中: {admins}")
            else:
                logger.debug(f"[Sleep] 用户 {sender_id} 是管理员")
            
            return is_admin
            
        except Exception as e:
            logger.error(f"[Sleep] 检查管理员权限时出错: {e}")
            return False

    async def _update_group_card(
        self, event: AstrMessageEvent, origin: str, remaining_minutes: int
    ) -> None:
        """更新群昵称显示剩余时长"""
        if not self.group_card_enabled:
            return

        # 只处理 aiocqhttp 平台的事件
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            if not isinstance(event, AiocqhttpMessageEvent):
                return
        except ImportError:
            logger.debug("[Sleep] aiocqhttp 模块未安装，跳过群昵称更新")
            return

        # 检查是否是群聊
        group_id = event.get_group_id()
        if not group_id:
            return

        # 获取 bot 实例
        bot = getattr(event, "bot", None)
        if not bot or not hasattr(bot, "call_action"):
            logger.debug("[Sleep] bot 不支持 call_action，跳过群昵称更新")
            return

        # 获取 bot 的 QQ 号
        self_id = event.get_self_id()
        if not self_id:
            return

        try:
            # 保存原始群昵称和QQ昵称(如果还没保存)
            if origin not in self.original_group_cards:
                try:
                    member_info = await bot.call_action(
                        "get_group_member_info",
                        group_id=int(group_id),
                        user_id=int(self_id),
                        no_cache=True,
                    )
                    # 群昵称(群名片)
                    self.original_group_cards[origin] = (
                        member_info.get("card", "") or ""
                    )
                    # QQ昵称
                    self.original_nicknames[origin] = (
                        member_info.get("nickname", "") or ""
                    )
                    logger.debug(
                        f"[Sleep] 保存原始信息 | 群昵称: {self.original_group_cards[origin]} | QQ昵称: {self.original_nicknames[origin]}"
                    )
                except Exception as e:
                    logger.debug(f"[Sleep] 获取原始群昵称失败: {e}")
                    self.original_group_cards[origin] = ""
                    self.original_nicknames[origin] = ""

            # 格式化群昵称
            if remaining_minutes > 0:
                # 获取原始信息用于占位符
                original_card = self.original_group_cards.get(origin, "")
                original_nickname = self.original_nicknames.get(origin, "")

                # 使用原始群昵称或QQ昵称(优先使用群昵称)
                original_name = original_card if original_card else original_nickname

                try:
                    card = self.group_card_template.format(
                        remaining=remaining_minutes,
                        original_card=original_card,
                        original_nickname=original_nickname,
                        original_name=original_name,
                    )
                except KeyError as e:
                    logger.warning(f"[Sleep] 群昵称模板占位符错误: {e}，使用默认格式")
                    card = f"[睡觉中 {remaining_minutes}分钟]"
            else:
                # 恢复原始群昵称
                card = self.original_group_cards.get(origin, "")

            # 更新群昵称
            await bot.call_action(
                "set_group_card",
                group_id=int(group_id),
                user_id=int(self_id),
                card=card[:60],  # QQ 群昵称最长 60 字符
            )
            logger.info(f"[Sleep] 已更新群昵称: {card[:60]}")

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
                await asyncio.sleep(60)  # 每分钟更新一次

                if not self.sleep_map:
                    continue

                current_time = time.time()
                for origin, expiry in list(self.sleep_map.items()):
                    remaining_seconds = expiry - current_time
                    if remaining_seconds > 0:
                        remaining_minutes = max(1, int(remaining_seconds / 60))
                        # 从映射中获取 event
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            await self._update_group_card(
                                event, origin, remaining_minutes
                            )
                    else:
                        # 过期了，恢复原始群昵称
                        event = self.origin_to_event_map.get(origin)
                        if event:
                            await self._update_group_card(event, origin, 0)
                        self.original_group_cards.pop(origin, None)
                        self.original_nicknames.pop(origin, None)
                        self.origin_to_event_map.pop(origin, None)
                        # 从 sleep_map 中移除过期的记录
                        self.sleep_map.pop(origin, None)
                        self._save_sleep_map()
                        logger.info(f"[Sleep] ⏰ 睡觉已自动结束 | 来源: {origin}")

        except asyncio.CancelledError:
            logger.info("[Sleep] 群昵称更新任务已停止")
        except Exception as e:
            logger.error(f"[Sleep] 群昵称更新任务异常: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def handle_message(self, event: AstrMessageEvent):
        text = event.get_message_str().strip()
        origin = event.unified_msg_origin

        # 1. 检查是否是控制指令
        is_sleep_cmd = any(text.startswith(cmd) for cmd in self.sleep_cmds)
        is_wake_cmd = any(text.startswith(cmd) for cmd in self.wake_cmds)

        # 2. 处理控制指令(需要检查前缀和权限)
        if is_sleep_cmd or is_wake_cmd:
            if not self._check_prefix(event):
                return

            # 检查管理员权限
            if not self._check_admin(event):
                event.set_result(
                    event.create_result()
                    .message("⚠️ 只有管理员才能使用此指令")
                    .use_t2i(False)
                )
                event.stop_event()
                return

            if is_sleep_cmd:
                result = await self._handle_sleep_command(event, text, origin)
                event.set_result(event.create_result().message(result).use_t2i(False))
                event.stop_event()
                return

            if is_wake_cmd:
                result = await self._handle_wake_command(event, origin)
                event.set_result(event.create_result().message(result).use_t2i(False))
                event.stop_event()
                return

        # 3. 检查定时睡觉
        if self._is_in_scheduled_time():
            logger.info("[Sleep] ⏰ 定时睡觉生效中")
            event.should_call_llm(False)
            event.stop_event()
            return

        # 4. 检查手动禁言状态
        expiry = self.sleep_map.get(origin)
        if expiry:
            if time.time() < expiry:
                remaining = int(expiry - time.time())
                logger.info(
                    f"[Sleep] 😴 消息已拦截 | 来源: {origin} | 剩余: {remaining}s"
                )
                event.should_call_llm(False)
                event.stop_event()
            else:
                # 禁言已过期，自动清理并恢复群昵称
                logger.info("[Sleep] ⏰ 睡觉已自动结束")
                self.sleep_map.pop(origin, None)
                self._save_sleep_map()
                
                # 修复：恢复群昵称
                if self.group_card_enabled:
                    saved_event = self.origin_to_event_map.get(origin)
                    if saved_event:
                        await self._update_group_card(saved_event, origin, 0)
                    self.original_group_cards.pop(origin, None)
                    self.original_nicknames.pop(origin, None)
                    self.origin_to_event_map.pop(origin, None)
                
                return

    async def _handle_sleep_command(
        self, event: AstrMessageEvent, text: str, origin: str
    ) -> str:
        """处理睡觉指令"""
        # 解析时长
        for cmd in self.sleep_cmds:
            if text.startswith(cmd):
                match = re.match(rf"^{re.escape(cmd)}\s*(\d+)([smhd])?", text)
                if match:
                    val = int(match.group(1))
                    unit = match.group(2) or "s"
                    duration = val * self.TIME_UNITS.get(unit, 1)
                else:
                    duration = self.default_duration
                break

        # 设置禁言
        self.sleep_map[origin] = time.time() + duration
        self._save_sleep_map()

        # 保存 event 到映射（用于后台更新）
        self.origin_to_event_map[origin] = event

        # 启动群昵称更新任务(如果还没启动)
        await self._ensure_update_task_started()

        # 立即更新群昵称(如果启用)
        if self.group_card_enabled:
            remaining_minutes = max(1, int(duration / 60))
            await self._update_group_card(event, origin, remaining_minutes)

        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
        )
        logger.info(f"[Sleep] 😴 已开始睡觉 | 时长: {duration}s | 到期: {expiry_time}")

        return self.sleep_reply.format(duration=duration, expiry_time=expiry_time)

    async def _handle_wake_command(
        self, event: AstrMessageEvent, origin: str
    ) -> str:
        """处理起床指令"""
        # 计算已睡觉时长
        old_expiry = self.sleep_map.get(origin)
        if old_expiry:
            now = time.time()
            duration = int(max(0, now - (old_expiry - self.default_duration)))
        else:
            duration = 0

        # 解除禁言
        self.sleep_map.pop(origin, None)
        self._save_sleep_map()

        # 恢复原始群昵称(如果启用)
        if self.group_card_enabled:
            await self._update_group_card(event, origin, 0)
            self.original_group_cards.pop(origin, None)
            self.original_nicknames.pop(origin, None)
            self.origin_to_event_map.pop(origin, None)

        expiry_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        logger.info(f"[Sleep] ☀️ 已起床 | 已睡觉: {duration}s")

        return self.wake_reply.format(duration=duration, expiry_time=expiry_time)

    @filter.llm_tool(name="sleep")
    async def llm_sleep(self, event: AstrMessageEvent, duration: int, unit: str = "m"):
        """在指定时间内停止回复消息。当用户表达希望你暂时睡觉,保持安静,不要再说话时,可以调用此工具

        Args:
            duration(number): 睡觉时长数值，由 LLM 根据用户意图自主决定合适的时长，最长不超过 60 分钟
            unit(string): 时间单位，可选值: s(秒), m(分钟), h(小时)。默认为 m(分钟)
        """
        # 检查是否启用 LLM 工具
        if not self.config.get("llm_tool_enabled", False):
            return "LLM 工具未启用"

        # 计算实际时长（秒）
        duration_seconds = duration * self.TIME_UNITS.get(unit, 60)

        # 限制最大时长为 60 分钟（3600 秒）
        max_duration = 3600
        if duration_seconds > max_duration:
            duration_seconds = max_duration
            logger.warning(
                f"[Sleep] ⚠️ LLM 请求的时长超过限制，已调整为最大值 {max_duration}s"
            )

        # 复用现有的睡觉逻辑
        origin = event.unified_msg_origin
        self.sleep_map[origin] = time.time() + duration_seconds
        self._save_sleep_map()

        # 保存 event 到映射
        self.origin_to_event_map[origin] = event

        # 启动群昵称更新任务
        await self._ensure_update_task_started()

        # 更新群昵称
        if self.group_card_enabled:
            remaining_minutes = max(1, int(duration_seconds / 60))
            await self._update_group_card(event, origin, remaining_minutes)

        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.sleep_map[origin])
        )
        logger.info(
            f"[Sleep] 😴 LLM 调用睡觉 | 时长: {duration_seconds}s | 到期: {expiry_time}"
        )

        return f"已设置睡觉 {int(duration_seconds/60)} 分钟，到期时间: {expiry_time}"

    async def terminate(self):
        # 停止群昵称更新任务
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

        # 恢复所有群昵称
        if self.group_card_enabled and self.original_group_cards:
            for origin in list(self.original_group_cards.keys()):
                event = self.origin_to_event_map.get(origin)
                if event:
                    await self._update_group_card(event, origin, 0)

        logger.info("[Sleep] 已卸载插件")
