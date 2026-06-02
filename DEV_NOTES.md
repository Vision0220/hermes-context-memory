# DEV_NOTES — 开发笔记

## 已知限制

### Windows 窗口信息采集

`pygetwindow` 在某些窗口类型下可能无法获取进程名。备选方案是通过 Windows 原生 API（ctypes）获取。当前实现了两个路径：先尝试 pygetwindow，失败则尝试 ctypes Win32 API。

### sqlite-vec 依赖

sqlite-vec 需要 C 编译环境。如果安装失败，项目自动退化为纯 FTS5 检索，功能不受影响（只是没有向量相似度排序）。

### VLM 和 Embedding 均为可选

两者都默认禁用。核心功能（截图、窗口记录、FTS 检索、CLI、REST API）不依赖任何外部 AI 服务。

## 测试环境

- Windows 11 Home China
- Python 3.11+
- uv 包管理器

## 开发顺序

Phase 1 ✅ 项目骨架（配置、模型、存储、隐私、服务器、CLI）
Phase 2 ✅ 采集层（截图、窗口信息、去重、浏览器捕获）
Phase 3 ✅ 检索层（FTS5、REST API、CLI recall）
Phase 4 ✅ 处理层（VLM、Embedding、Sessionizer — 接口已实现，调用可选）
Phase 5 ✅ 集成（浏览器扩展、MCP Server、测试、README）
