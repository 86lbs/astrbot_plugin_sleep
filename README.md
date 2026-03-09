# AstrBot 睡觉插件

让 Bot 暂时保持安静的插件，支持多种触发方式和智能场景检测。

## 功能特性

- 🛏️ **指令控制**：通过指令让 Bot 睡觉/起床
- 🤖 **LLM 工具调用**：支持 LLM 自主判断并触发睡觉
- ⏰ **定时睡觉**：在指定时间段自动睡觉
- 📊 **刷屏检测**：检测群聊刷屏并自动睡觉
- 🚫 **拒绝敏感内容**：遇到不当内容时自动静默
- 🏷️ **群昵称更新**：睡觉时更新群昵称显示剩余时间
- 🔐 **权限分离**：睡觉和起床可分别配置管理员权限

## 安装

在 AstrBot 插件市场搜索 `astrbot_plugin_sleep` 或手动安装：

```bash
git clone https://github.com/86lbs/astrbot_plugin_sleep.git
```

## 配置说明

### 基础配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `sleep_commands` | `睡觉,sleep` | 睡觉指令，多个用逗号分隔 |
| `wake_commands` | `起床,醒来,wake` | 起床指令，多个用逗号分隔 |
| `require_prefix` | `false` | 是否需要前缀触发 |
| `sleep_require_admin` | `false` | 睡觉是否需要管理员权限 |
| `wake_require_admin` | `false` | 起床是否需要管理员权限 |

### 时长配置

| 配置项 | 默认值 | 范围 | 说明 |
|--------|--------|------|------|
| `default_duration` | 600秒 (10分钟) | 60-86400秒 | 默认睡觉时长 |
| `max_duration_command` | 43200秒 (12小时) | 60-86400秒 | 指令触发最大时长 |
| `max_duration_auto` | 10800秒 (3小时) | 60-86400秒 | 自判定休眠最大时长 |

### 回复语配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `sleep_reply` | `好的，我去睡觉了~💤` | 睡觉回复语 |
| `wake_reply` | `早安~我醒来了☀️` | 起床回复语 |

支持变量：`{duration}`(时长秒)、`{expiry_time}`(到期时间)

### 定时睡觉配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `scheduled_sleep_enabled` | `false` | 启用定时睡觉 |
| `scheduled_sleep_times` | `23:00-07:00` | 睡觉时间段，每行一个 |

**时间段格式：**
```
23:00-07:00
12:00-14:00
```

### 刷屏检测配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `spam_detect_enabled` | `false` | 启用刷屏检测 |
| `spam_threshold` | `10` | 刷屏判定阈值（消息数） |
| `spam_window` | `60` | 检测窗口（秒） |
| `spam_auto_sleep_duration` | `1800` | 刷屏自动睡觉时长（秒） |

### 群昵称配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `group_card_update_enabled` | `false` | 启用群昵称更新 |
| `group_card_template` | `{original_name}[睡觉中 {remaining}]` | 指令触发的群昵称模板 |
| `group_card_template_auto` | `{original_name}[静默中 {remaining}]` | 自判定休眠的群昵称模板 |

**支持的变量：**
- `{original_name}` - 原始昵称（优先群名片）
- `{original_card}` - 原始群名片
- `{original_nickname}` - 原始QQ昵称
- `{remaining}` - 剩余时间（如 `2.5小时` 或 `45分钟`）
- `{remaining_seconds}` - 剩余秒数

### LLM 工具配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `llm_tool_enabled` | `true` | 启用 LLM 工具 |

## 使用方法

### 指令使用

```
睡觉          # 使用默认时长睡觉
睡觉 30       # 睡觉30秒
睡觉 30m      # 睡觉30分钟
睡觉 2h       # 睡觉2小时

起床          # 叫醒 Bot
```

### LLM 工具

插件提供两个 LLM 工具供 AI 自主调用：

#### 1. `sleep` - 简单睡觉

当用户表达希望 Bot 暂时睡觉、保持安静时调用。

**参数：**
- `duration`：睡觉时长数值（由 LLM 自主决定）
- `unit`：时间单位（s/m/h，默认 m）

#### 2. `sleep_until_calm` - 智能休眠

适用于以下场景：
1. 检测到群聊刷屏或消息过多
2. 用户要求讨论不适当内容（色情、暴力、违法等）
3. 需要拒绝回答敏感问题
4. 其他需要暂时保持安静的情况

**参数：**
- `duration`：睡觉时长（分钟），由 LLM 根据情况自主决定
  - 刷屏严重：30-60 分钟
  - 拒绝敏感内容：5-15 分钟
  - 消息稍多：10-20 分钟
- `auto_wake_threshold`：自动起床的消息速率阈值，设为 0 则只能手动唤醒
- `reason`：睡觉原因

## 时间显示格式

| 剩余时间 | 显示格式 |
|----------|----------|
| ≥ 1小时 | `X.X小时` (如 `2.5小时`) |
| < 1小时 | `X分钟` (如 `45分钟`) |

## 权限配置示例

### 场景 1：所有人可控制

```json
{
    "sleep_require_admin": false,
    "wake_require_admin": false
}
```

### 场景 2：只有管理员能控制

```json
{
    "sleep_require_admin": true,
    "wake_require_admin": true
}
```

### 场景 3：所有人能让睡，只有管理员能叫醒

```json
{
    "sleep_require_admin": false,
    "wake_require_admin": true
}
```

## 更新记录

### v1.4.0 (2025-01-XX)

**新功能：**
- 刷屏检测配置项化：`spam_threshold`、`spam_window`、`spam_auto_sleep_duration`
- `sleep_until_calm` 的 `duration` 参数可由 LLM 自主定义
- `sleep` 工具的 `duration` 参数也可由 LLM 自主定义

**改进：**
- 工具描述更新，引导 LLM 根据情况自主决定合适时长
- 日志输出增加刷屏检测配置信息

### v1.3.0 (2025-01-XX)

**新功能：**
- 新增 `max_duration_command` 配置项：指令触发最大时长（默认12小时）
- 新增 `max_duration_auto` 配置项：自判定休眠最大时长（默认3小时）
- 新增 `default_duration` 配置项：默认睡觉时长（默认10分钟）
- `sleep_until_calm` 工具扩展支持拒绝回答场景（色情、暴力、违法等敏感内容）
- `auto_wake_threshold` 设为 0 时可禁用自动起床功能

**改进：**
- 时长配置支持自定义，范围 60-86400 秒
- 日志输出增加时长配置信息
- 新增 `_format_duration()` 方法格式化时长显示

### v1.2.0 (2025-01-XX)

**新功能：**
- 指令触发最大时长限制为12小时
- 自判定休眠(LLM工具)最大时长限制为3小时
- 自判定休眠使用独立的群昵称模板 (`group_card_template_auto`)
- 剩余时间大于1小时时显示为 `X.X小时` 格式

**改进：**
- 新增 `_format_remaining_time()` 方法格式化时间显示
- 群昵称模板支持 `{remaining_seconds}` 变量
- 更新配置文件，添加 `group_card_template_auto` 配置项

### v1.1.0 (2025-01-XX)

**新功能：**
- 分离睡觉和起床的管理员权限配置 (`sleep_require_admin`, `wake_require_admin`)
- 新增 LLM 工具 `sleep_until_calm`，支持刷屏检测自动睡觉
- 自动睡觉后可根据群消息速率自动起床
- 添加群消息计数器和刷屏检测配置

**配置项变更：**
- 移除 `require_admin`，改为 `sleep_require_admin` 和 `wake_require_admin`
- 新增 `spam_detect_enabled`、`spam_threshold`、`spam_window` 配置

### v1.0.2 (2025-01-XX)

**修复：**
- 将 `event.create_result().message()` 改为 `yield event.plain_result()`
- 根据 AstrBot 官方文档修正消息回复方式

### v1.0.1 (2025-01-XX)

**修复：**
- 修复管理员权限检查逻辑
- 修复配置保存问题

### v1.0.0 (2025-01-XX)

**初始版本：**
- 基础睡觉/起床指令
- 定时睡觉功能
- 群昵称更新功能
- LLM 工具 `sleep`

## 许可证

MIT License

## 作者

86lbs

## 反馈与支持

- GitHub Issues: https://github.com/86lbs/astrbot_plugin_sleep/issues
- AstrBot 社区: https://astrbot.app
