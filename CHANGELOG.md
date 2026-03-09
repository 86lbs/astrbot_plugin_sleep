# 更新记录

## v1.4.0 (2025-01-XX)

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

## v1.3.0 (2025-01-XX)

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

## v1.2.0 (2025-01-XX)

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

## v1.1.0 (2025-01-XX)

### 新功能

- 分离睡觉和起床的管理员权限配置 (`sleep_require_admin`, `wake_require_admin`)
- 新增 LLM 工具 `sleep_until_calm`，支持刷屏检测自动睡觉
- 自动睡觉后可根据群消息速率自动起床
- 添加群消息计数器和刷屏检测配置

### 配置项变更

- 移除 `require_admin`，改为 `sleep_require_admin` 和 `wake_require_admin`
- 新增 `spam_detect_enabled`、`spam_threshold`、`spam_window` 配置

---

## v1.0.2 (2025-01-XX)

### 修复

- 将 `event.create_result().message()` 改为 `yield event.plain_result()`
- 根据 AstrBot 官方文档修正消息回复方式

---

## v1.0.1 (2025-01-XX)

### 修复

- 修复管理员权限检查逻辑
- 修复配置保存问题

---

## v1.0.0 (2025-01-XX)

### 初始版本

- 基础睡觉/起床指令
- 定时睡觉功能
- 群昵称更新功能
- LLM 工具 `sleep`
