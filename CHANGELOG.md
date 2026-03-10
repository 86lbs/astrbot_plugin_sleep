# 更新记录

## v1.6.0 (2026-03-10)

### 新功能

- **基于时间戳的动态解锁码**
  - 解锁码现在会随时间变化（TOTP风格）
  - 新增 `unlock_code_interval` 配置项：解锁码有效期（默认60秒）
  - 验证时支持当前时间步和前一个时间步（允许时间误差）
  - 增加安全性：即使解锁码泄露，也会在有效期后失效

### 改进

- 更新锁定提示模板，显示解锁码有效期
- 新增模板变量 `{unlock_code_interval}`

---

## v1.5.5 (2026-03-10)

### 修复

- 修复指令配置项格式错误
- `sleep_commands` 和 `wake_commands` 改回 `list` 类型
- 保持与原配置文件格式一致

---

## v1.5.4 (2026-03-10)

### 修复

- 更新 `_conf_schema.json` 文件，添加所有新增的配置项
- 解决配置项在 AstrBot 管理面板不显示的问题

---

## v1.5.3 (2026-03-10)

### 新功能

- **紧急解锁指令**：管理员发送"强制解锁"可直接解锁（兜底机制）
- 加载锁定记录出错时自动清空，防止卡死

### 改进

- 锁定状态下增加解锁提示日志
- 优化错误处理逻辑

---

## v1.5.2 (2026-03-10)

### 新功能

- **自定义锁定提示模板**
  - 新增 `lock_reply_template` 配置项：触发锁定时的提示模板
  - 新增 `locked_reply_template` 配置项：锁定后发送消息时的提示模板
  - 支持变量：`{reason}`, `{lock_time}`, `{unlock_code}`, `{unlock_command}`, `{group_id}`

### 改进

- 锁定提示支持完全自定义
- 模板占位符错误时自动降级为默认提示

---

## v1.5.1 (2026-03-10)

### 新功能

- **兜底解锁机制**
  - 新增 `clear_lock_on_startup` 配置项（默认启用）
  - AstrBot 重启时自动清空所有敏感锁定记录
  - 插件卸载/退出时自动清空所有敏感锁定记录
  - 防止因重启或退出群聊导致永久锁定

### 改进

- 锁定记录文件 `locked.json` 在启动/退出时自动清理
- 日志输出增加兜底机制提示

---

## v1.5.0 (2026-03-09)

### 新功能

- **敏感内容锁定功能**
  - 新增 `lock_sensitive` LLM 工具，用于处理严重违规情况
  - 触发后无法直接解开，必须输入解锁码
  - 基于群号的 2FA 解锁码生成（HMAC-SHA256）
  - 新增 `lock_secret` 配置项：用于生成解锁码的密钥
  - 新增 `unlock_code_input` 配置项：输入解锁码
  - 新增 `unlock_command` 配置项：解锁指令（默认"解锁"）
  - 新增 `group_card_template_locked` 配置项：锁定时的群昵称模板

### 工具区分

- `sleep_until_calm`: 用于刷屏、消息过多等普通场景
- `lock_sensitive`: 用于色情、暴力、违法等严重违规场景

### 改进

- 敏感锁定状态会拦截所有消息并提示解锁方式
- 解锁码验证使用 HMAC 安全比较
- 解锁成功后自动清空配置中的解锁码

---

## v1.4.0 (2026-03-09)

### 新功能

- **刷屏检测配置化**
  - `spam_threshold`: 刷屏判定阈值（消息数）
  - `spam_window`: 刷屏检测窗口（秒）
  - `spam_auto_sleep_duration`: 刷屏自动睡觉时长（秒）

- **LLM 自主定义时长**
  - `sleep_until_calm` 的 `duration` 参数可由 LLM 自主定义
  - `sleep` 工具的 `duration` 参数也可由 LLM 自主定义

### 改进

- 工具描述更新，引导 LLM 根据情况自主决定合适时长
- 示例：刷屏严重可设置30-60分钟，拒绝敏感内容可设置5-15分钟
- 日志输出增加刷屏检测配置信息

### 配置项变更

- 新增 `spam_auto_sleep_duration` (默认1800秒/30分钟)
- 更新 `spam_threshold` 和 `spam_window` 的描述

---

## v1.3.0 (2026-03-09)

### 新功能

- 新增 `max_duration_command` 配置项：指令触发最大时长（默认12小时）
- 新增 `max_duration_auto` 配置项：自判定休眠最大时长（默认3小时）
- 新增 `default_duration` 配置项：默认睡觉时长（默认10分钟）
- `sleep_until_calm` 工具扩展支持拒绝回答场景（色情、暴力、违法等敏感内容）
- `auto_wake_threshold` 设为 0 时可禁用自动起床功能

### 改进

- 时长配置支持自定义，范围 60-86400 秒
- 日志输出增加时长配置信息
- 新增 `_format_duration()` 方法格式化时长显示

---

## v1.2.0 (2026-03-09)

### 新功能

- 指令触发最大时长限制为12小时
- 自判定休眠(LLM工具)最大时长限制为3小时
- 自判定休眠使用独立的群昵称模板 (`group_card_template_auto`)
- 剩余时间大于1小时时显示为 `X.X小时` 格式

### 改进

- 新增 `_format_remaining_time()` 方法格式化时间显示
- 群昵称模板支持 `{remaining_seconds}` 变量
- 更新配置文件，添加 `group_card_template_auto` 配置项

---

## v1.1.0 (2026-03-09)

### 新功能

- 分离睡觉和起床的管理员权限配置 (`sleep_require_admin`, `wake_require_admin`)
- 新增 LLM 工具 `sleep_until_calm`，支持刷屏检测自动睡觉
- 自动睡觉后可根据群消息速率自动起床
- 添加群消息计数器和刷屏检测配置

### 配置项变更

- 移除 `require_admin`，改为 `sleep_require_admin` 和 `wake_require_admin`
- 新增 `spam_detect_enabled`、`spam_threshold`、`spam_window` 配置

---

## v1.0.2 (2026-03-09)

### 修复

- 将 `event.create_result().message()` 改为 `yield event.plain_result()`
- 根据 AstrBot 官方文档修正消息回复方式

---

## v1.0.1 (2026-03-09)

### 修复

- 修复管理员权限检查逻辑
- 修复配置保存问题

---

## v1.0.0 (2026-03-09)

### 初始版本

- 基础睡觉/起床指令
- 定时睡觉功能
- 群昵称更新功能
- LLM 工具 `sleep`
