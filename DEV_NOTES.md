# DEV_NOTES.md — 技术债务

## 已修复 (本次验证)

1. **/ui f-string bug**: JS 花括号在 Python f-string 中被解释 → 用 `{{}}` 转义
2. **MCP FastMCP API**: `description` → `instructions`
3. **SSL 自签名证书**: httpx 添加 `verify=False`
4. **Secret 泄露**: filter-branch 清理 git 历史

## 技术债务

### 高优先级
1. **中文 FTS5 分词**: SQLite FTS5 默认不支持中文分词,搜索中文关键词返回空
   - 方案: 使用 jieba 分词预处理,或 VLM 摘要中生成英文关键词
2. **瓦片处理**: 5120x2160 图片应分块处理,只处理变化瓦片
   - 方案: 4x3 grid, 只对 text_density > 阈值的瓦片调用 VLM
3. **语义缓存**: 相同截图重复调用 VLM
   - 方案: 以 thumbnail_md5 为 key 缓存 VLM 结果

### 中优先级
4. **sessionizer 集成**: 事件→会话聚合模块存在但未接入管线
5. **scheduler_metrics**: 调度器指标记录表已建但未写入
6. **VLM 超时处理**: 如果 VLM 响应 >60s,采集循环会阻塞
   - 方案: 用 asyncio.wait_for 包装,超时则 fallback

### 低优先级
7. **sqlite-vec 向量检索**: 模块存在但未在 search.py 中集成
8. **截图目录按 monitor_id 分目录**: 当前所有截图在同一目录
9. **浏览器扩展 popup 实时刷新**: 当前 popup 只在打开时读取一次状态

## 环境特定问题

- **Windows GBK 编码**: Rich console 输出中文/Unicode 可能报错 → CLI 已强制 UTF-8
- **pygetwindow 局限**: 某些窗口类型无法获取进程名 → Win32 API fallback
- **WSL2 截图**: WSL2 无法截取 Windows 桌面 → 必须在 Windows 原生 Python 运行
