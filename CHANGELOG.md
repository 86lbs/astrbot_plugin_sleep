# Changelog

All notable changes to this project will be documented in this file.

## [v1.3.1] - 2025-03-09

### Fixed
- **严重修复**：默认时间单位从秒改为分钟，与 README 文档说明一致（第 802 行）
  - 修复前：输入 `睡觉 10` 会被解析为 10 秒
  - 修复后：输入 `睡觉 10` 会被解析为 10 分钟
- **严重修复**：自动起床通知发送失败的问题（第 688 行）
  - 修复前：在清理数据后才获取 event，导致返回 None
  - 修复后：先获取 event，再清理数据
- **修复**：起床时已睡觉时长计算错误（第 849 行）
  - 改进了时长计算逻辑，区分普通睡觉和自判定休眠

### Changed
- **优化**：添加异步锁保护共享数据的并发访问
  - `sleep_map` 和 `auto_wake_sleep_map` 现在使用 `asyncio.Lock` 保护
  - 避免多任务并发修改导致的数据不一致
- **优化**：移除不可靠的配置修改代码（第 133 行）
  - 不再尝试直接修改 AstrBotConfig 对象
- **优化**：统一跨天时间判断的边界处理（第 373 行）
  - 不跨天和跨天情况现在使用一致的边界逻辑

### Added
- **新增**：类型注解改进
  - 使用 `List[str]`、`Dict[str, Any]` 等标准类型注解
  - 提高代码可读性和 IDE 支持
- **新增**：`DEFAULT_TIME_UNIT` 常量
  - 统一管理默认时间单位配置

### Security
- **安全**：配置文件字段一致性修复
  - `_conf_schema.json` 和 `config.json` 字段现在完全一致
  - 移除了不存在的 `require_admin` 字段，使用 `sleep_require_admin` 和 `wake_require_admin`

---

## [v1.3.0] - 2025-03-08

### Fixed
- LLM tool 调用失败的问题

### Changed
- 参数类型转换和验证
- 代码结构，提取公共方法
- 异常处理和错误提示
- 配置文件一致性

### Added
- 详细的代码注释

---

## [v1.0.0] - 2025-03-01

### Added
- 基于 astrbot_plugin_shutup 重构
- 手动睡觉/起床指令
- 定时睡觉功能
- LLM 工具调用
- 群昵称状态显示
- 管理员权限控制
- 刷屏检测自动睡觉

### Fixed
- 睡觉结束后群昵称未恢复的问题
- 管理员权限识别问题

### Changed
- 重命名：闭嘴 → 睡觉
