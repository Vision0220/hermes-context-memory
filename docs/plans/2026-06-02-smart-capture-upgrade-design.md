# Hermes Context Memory — 智能采集升级设计

**日期**: 2026-06-02
**状态**: 已批准

## 概述

本次升级为 Hermes Context Memory 增加 5 项核心能力：
1. 多屏截图支持（per-monitor 独立采集）
2. 高分辨率智能处理（5120×2160 场景）
3. 多信号级联去重管线（90%+ VLM 调用削减）
4. VLM/Embedding API 集成（含 GPU 预热）
5. 自适应截图频率 + 队列背压

## 1. 多屏截图

**方案**: per-monitor 独立截图

- mss 支持 `sct.monitors[1]`, `sct.monitors[2]`, ... 按物理显示器采集
- 每个屏幕独立保存、独立 hash、独立去重
- `RawEvent` 增加 `monitor_id` 字段
- `window.py` 增加 Win32 `MonitorFromWindow` API 获取活动窗口所在显示器

**配置新增**:
```yaml
capture:
  per_monitor: true
  monitors: []  # 空=全部, [1,2]=指定
```

## 2. 高分辨率处理

**方案**: 智能多级缩放

| 用途 | 宽度 | 说明 |
|------|------|------|
| 原始存储 | 全分辨率 | 保存到 data/screenshots/ |
| Hash 计算 | 640px | 生成缩略图计算 hash |
| VLM 发送 | 2048px | VLM 兼容性 |
| 持久存储 | max_width (1600px) | 用于长期保存 |

**配置新增**:
```yaml
capture:
  vlm_max_width: 2048
  hash_max_width: 640
```

## 3. 多信号级联去重管线

**方案**: 渐进式级联过滤，早停早判

```
截图 → [0.1ms]  元数据变化检测 (app/window/title 变化)
     → [0.3ms]  缩略图 MD5 快速比对 (64×36 像素)
     → [1.5ms]  dHash 感知哈希 (汉明距离 ≤6 = 相似)
     → [5ms]    SSIM 结构相似度 (仅 dHash 距离 6-12 时)
     → 入队等待 VLM
```

**预期效果**: 只有 ~1% 的帧最终调用 VLM

**关键决策**:
- dHash 替代 pHash（更适合屏幕文字/边缘，速度快 2x）
- 缩略图 MD5 作为第一级（<0.3ms，淘汰 ~50%）
- SSIM 仅在边界 case 调用（dHash 距离 6-12）
- per-monitor 独立去重历史

**配置新增**:
```yaml
capture:
  dedup:
    hash_algorithm: "dhash"  # dhash/phash
    hash_threshold: 6        # 汉明距离阈值
    ssim_threshold: 0.85     # SSIM 相似度阈值
    thumbnail_size: [64, 36] # 缩略图尺寸
```

## 4. VLM/Embedding API 集成

### 4A. API 配置

```yaml
models:
  vlm:
    enabled: true
    base_url: "https://your-api-url/v1"
    api_key: "your-api-key-here"
    model: "qwen/qwen3.6-35b-a3b"
    max_tokens: 1024
    temperature: 0.1
    timeout: 60
    retry_count: 2
  embedding:
    enabled: true
    base_url: "https://your-api-url/v1"
    api_key: "your-api-key-here"
    model: "text-embedding-qwen3-embedding-4b"
    timeout: 30
    retry_count: 2
```

### 4B. GPU 预热流程

```
服务启动 →
  1. VLM 预热：发送小图片 + 简单 prompt → 等待成功
  2. Embedding 预热：发送短文本 → 等待成功
  3. 两者就绪后启动采集循环
```

VLM 优先加载（GPU 内存更大），Embedding 后加载。

### 4C. 处理管线集成

```
截图保存 → hash 去重 → 不重复时：
  1. 异步提交 VLM 分析（不阻塞采集循环）
  2. VLM 完成 → 更新 DB 的 vlm_summary/vlm_json
  3. 异步提交 Embedding
  4. Embedding 完成 → 存储向量到 recall_chunks
```

### 4D. 连接池

- 全局共享 `httpx.AsyncClient`（连接复用）
- VLM 和 Embedding 各一个客户端实例
- 启动时创建，关闭时清理

## 5. 自适应截图频率 + 队列背压

### 5A. 空闲检测状态机

| 级别 | 条件 | 截图间隔 | VLM |
|------|------|----------|-----|
| L0 Immediate | App/窗口切换 | 立即 | 是 |
| L1 Active | 有键盘/鼠标输入 | 15s | 条件 |
| L2 Semi-Idle | 无输入 10-60s | 30s | hash 变化时 |
| L3 Idle | 无输入 60s+ | 120s | 否 |
| L4 Paused | 屏幕锁定 | 停止 | 否 |

**输入检测**: Windows `GetLastInputInfo` API（ctypes，零依赖，<1ms）

### 5B. 队列背压

```
VLM 处理队列 (asyncio.Queue, maxsize=10)：
  入队时队列满 → 丢弃最旧帧（保留首尾）
  队列 > 50% → 采集间隔翻倍
  队列空闲 → 恢复基准间隔
```

### 5C. 自适应间隔公式

```python
interval = base_interval × pressure_factor × idle_factor
# pressure_factor: 1.0 (队列空), 2.0 (>50%), 4.0 (>80%)
# idle_factor: L0=1, L1=1, L2=2, L3=8, L4=∞
# 范围限制: [5s, 300s]
```

## 实现顺序（TDD）

| Phase | 内容 | 新增/修改文件 |
|-------|------|--------------|
| P1 | 多屏截图 + 高分辨率 | capture/screen.py, models.py, storage.py, config.py |
| P2 | 级联去重管线 | capture/dedup.py (重写) |
| P3 | VLM/Embedding API 集成 | processing/vlm.py, processing/embedding.py, config.py |
| P4 | GPU 预热 + 连接池 | server/main.py (lifespan), processing/vlm.py |
| P5 | 自适应频率 + 队列背压 | server/routes.py (capture_loop 重写), capture/idle.py (新增) |
| P6 | 采集循环集成 | server/routes.py（完整重写 capture_loop）|
| P7 | 测试 + 文档 | tests/, README.md |

每个 Phase 先写测试（TDD），再实现。
