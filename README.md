# AstrBot 睡觉插件

让 bot 暂时保持安静的 AstrBot 插件。

## 功能特性

- 🛏️ **手动睡觉/起床**：通过指令让 bot 暂时保持安静
- ⏰ **定时睡觉**：配置固定时间段自动睡觉
- 🤖 **LLM 工具调用**：LLM 可主动调用睡觉功能
- 📝 **群昵称状态显示**：睡觉期间自动修改群昵称显示剩余时长
- 🔒 **管理员权限控制**：可限制只有管理员才能使用指令

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
| `require_prefix` | bool | true | 是否需要命令前缀 |
| `priority` | int | 10000 | 插件优先级 |
| `scheduled_sleep_enabled` | bool | false | 启用定时睡觉 |
| `scheduled_sleep_times` | text | "23:00-07:00" | 定时睡觉时间段 |
| `group_card_update_enabled` | bool | false | 启用群昵称显示 |
| `group_card_template` | string | "{original_name}[睡觉中 {remaining}分钟]" | 群昵称模板 |
| `llm_tool_enabled` | bool | false | 启用 LLM 工具调用 |
| `require_admin` | bool | false | 需要管理员权限 |

## 更新日志

### v1.0.0
- 基于 astrbot_plugin_shutup 重构
- 修复：睡觉结束后群昵称未恢复的问题
- 修复：管理员权限识别问题
- 重命名：闭嘴 → 睡觉

## 许可证

MIT License
