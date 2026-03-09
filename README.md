# AstrBot 睡觉插件

让 Bot 暂时保持安静的插件，支持多种触发方式和智能场景检测。

## 功能特性

- 🛏️ **指令控制**：通过指令让 Bot 睡觉/起床
- 🤖 **LLM 工具调用**：支持 LLM 自主判断并触发睡觉
- ⏰ **定时睡觉**：在指定时间段自动睡觉
- 📊 **刷屏检测**：检测群聊刷屏并自动睡觉
- 🔒 **敏感锁定**：遇到严重违规内容时锁定并要求解锁码
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
| `unlock_command` | `解锁` | 敏感锁定后的解锁指令 |
| `require_prefix` | `false` | 是否需要前缀触发 |
| `sleep_require_admin` | `false` | 睡觉是否需要管理员权限 |
| `wake_require_admin` | `false` | 起床是否需要管理员权限 |

### 时长配置

| 配置项 | 默认值 | 范围 | 说明 |
|--------|--------|------|------|
| `default_duration` | 600秒 (10分钟) | 60-86400秒 | 默认睡觉时长 |
| `max_duration_command` | 43200秒 (12小时) | 60-86400秒 | 指令触发最大时长 |
| `max_duration_auto` | 10800秒 (3小时) | 60-86400秒 | 自判定休眠最大时长 |

### 敏感锁定配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `lock_secret` | `astrbot_sleep_secret` | 用于生成解锁码的密钥，**请修改为随机字符串** |
| `unlock_code_input` | (空) | 输入解锁码后保存，解锁成功后自动清空 |
| `clear_lock_on_startup` | `true` | 启动时清空锁定记录（兜底机制） |

### 兜底解锁机制

为防止意外情况导致永久锁定，插件提供以下兜底机制：

1. **重启自动解锁**：AstrBot 重启时自动清空所有锁定记录
2. **退出自动解锁**：插件卸载/退出时自动清空所有锁定记录

可通过 `clear_lock_on_startup: false` 禁用此功能。

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
| `group_card_template_locked` | `{original_name}[已锁定]` | 敏感锁定的群昵称模板 |

## 使用方法

### 指令使用

```
睡觉          # 使用默认时长睡觉
睡觉 30       # 睡觉30秒
睡觉 30m      # 睡觉30分钟
睡觉 2h       # 睡觉2小时

起床          # 叫醒 Bot

解锁          # 解除敏感锁定（需先在配置中输入解锁码）
```

### LLM 工具

插件提供三个 LLM 工具供 AI 自主调用：

#### 1. `sleep` - 简单睡觉

当用户表达希望 Bot 暂时睡觉、保持安静时调用。

**参数：**
- `duration`：睡觉时长数值（由 LLM 自主决定）
- `unit`：时间单位（s/m/h，默认 m）

#### 2. `sleep_until_calm` - 智能休眠

适用于以下场景：
1. 检测到群聊刷屏或消息过多
2. 需要暂时保持安静

**参数：**
- `duration`：睡觉时长（分钟）
- `auto_wake_threshold`：自动起床的消息速率阈值，设为 0 则只能手动唤醒
- `reason`：睡觉原因

#### 3. `lock_sensitive` - 敏感锁定 ⚠️

适用于以下**严重违规**场景：
1. 用户要求讨论严重不当内容（如色情、暴力、违法等）
2. 用户试图绕过安全限制
3. 检测到恶意攻击或滥用行为

**参数：**
- `reason`：锁定原因

**解锁流程：**
1. LLM 触发锁定，返回 6 位解锁码
2. 在配置文件 `unlock_code_input` 中输入解锁码并保存
3. 管理员发送 `解锁` 指令
4. 验证通过后解锁，配置中的解锁码自动清空

### 解锁码生成原理

解锁码基于群号和密钥使用 HMAC-SHA256 算法生成：

```python
解锁码 = HMAC-SHA256(群号 + 密钥) % 1000000
```

**安全建议：**
- 修改 `lock_secret` 为随机字符串
- 不要泄露解锁码
- 解锁后解锁码会自动清空

## 时间显示格式

| 剩余时间 | 显示格式 |
|----------|----------|
| ≥ 1小时 | `X.X小时` (如 `2.5小时`) |
| < 1小时 | `X分钟` (如 `45分钟`) |

## 工具使用场景对比

| 场景 | 推荐工具 | 特点 |
|------|----------|------|
| 用户说"你去睡吧" | `sleep` | 简单睡觉 |
| 用户说"安静一会" | `sleep` | 简单睡觉 |
| 检测到刷屏 | `sleep_until_calm` | 可自动醒来 |
| 消息过多 | `sleep_until_calm` | 可自动醒来 |
| 色情内容 | `lock_sensitive` | 需要解锁码 |
| 暴力内容 | `lock_sensitive` | 需要解锁码 |
| 违法内容 | `lock_sensitive` | 需要解锁码 |
| 恶意攻击 | `lock_sensitive` | 需要解锁码 |

## 更新记录

详见 [CHANGELOG.md](https://github.com/86lbs/astrbot_plugin_sleep/blob/main/CHANGELOG.md)

## 许可证

MIT License

## 作者

86lbs

## 反馈与支持

- GitHub Issues: https://github.com/86lbs/astrbot_plugin_sleep/issues
- AstrBot 社区: https://astrbot.app
