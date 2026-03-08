# AstrBot 睡觉插件

让 bot 暂时保持安静的 AstrBot 插件。

## 功能特性

- 🛏️ **手动睡觉/起床**：通过指令让 bot 暂时保持安静
- ⏰ **定时睡觉**：配置固定时间段自动睡觉
- 🤖 **LLM 工具调用**：LLM 可主动调用睡觉功能
- 📝 **群昵称状态显示**：睡觉期间自动修改群昵称显示剩余时长
- 🔒 **管理员权限控制**：可限制只有管理员才能使用指令
- 🔄 **刷屏检测自动睡觉**：检测到群消息过多时自动静默

## 安装

将插件文件夹放入 AstrBot 的 `plugins` 目录下，重启 AstrBot 即可。

## 使用方法

### 指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `睡觉 [时长][单位]` | 让 bot 睡觉 | `睡觉 10m`（睡觉10分钟） |
| `起床` / `醒来` | 唤醒 bot | `起床` |

**时间单位**：
- `s` - 秒
- `m` - 分钟（默认）
- `h` - 小时
- `d` - 天

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `sleep_commands` | list | ["睡觉", "sleep"] | 睡觉指令列表 |
| `wake_commands` | list | ["起床", "醒来", "wake"] | 起床指令列表 |
| `default_duration` | int | 600 | 默认睡觉时长(秒) |
| `sleep_reply` | string | "好的，我去睡觉了~💤" | 睡觉时的回复 |
| `wake_reply` | string | "早安~我醒来了☀️" | 起床时的回复 |
| `require_prefix` | bool | false | 是否需要命令前缀 |
| `priority` | int | 10000 | 插件优先级 |
| `scheduled_sleep_enabled` | bool | false | 启用定时睡觉 |
| `scheduled_sleep_times` | text | "23:00-07:00" | 定时睡觉时间段 |
| `group_card_update_enabled` | bool | false | 启用群昵称显示 |
| `group_card_template` | string | "{original_name}[睡觉中 {remaining}分钟]" | 群昵称模板 |
| `llm_tool_enabled` | bool | true | 启用 LLM 工具调用 |
| `require_admin` | bool | false | 需要管理员权限 |

## LLM 工具

本插件提供两个 LLM 工具：

### 1. `sleep` 工具

在指定时间内停止回复消息。

**参数**：
- `duration` (number): 睡觉时长数值，最长不超过 60 分钟
- `unit` (string): 时间单位，可选值: s(秒), m(分钟), h(小时)。默认为 m(分钟)

### 2. `sleep_until_calm` 工具

当检测到群聊刷屏或消息过多时，暂时睡觉保持安静，直到群消息减少或收到起床指令。

**参数**：
- `max_duration` (number): 最大睡觉时长（分钟），默认30分钟，最长3小时
- `auto_wake_threshold` (number): 自动起床的消息速率阈值（每分钟消息数），默认5条
- `reason` (string): 睡觉原因，如"群聊刷屏"、"消息过多"等

## 更新日志

### v1.3.0
- 修复：LLM tool 调用失败的问题
- 优化：参数类型转换和验证
- 优化：代码结构，提取公共方法
- 优化：异常处理和错误提示
- 优化：配置文件一致性
- 添加：详细的代码注释

### v1.0.0
- 基于 astrbot_plugin_shutup 重构
- 修复：睡觉结束后群昵称未恢复的问题
- 修复：管理员权限识别问题
- 重命名：闭嘴 → 睡觉

## 许可证

MIT License
