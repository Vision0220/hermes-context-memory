"""配置管理模块 — 从 config.yaml 和环境变量加载配置"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


# ── 项目根目录 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


# ── 子配置模型 ──────────────────────────────────────────────────

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1833


class DedupConfig(BaseModel):
    """去重管线配置。"""
    hash_algorithm: str = "dhash"  # dhash / phash
    hash_threshold: int = 6        # 汉明距离阈值
    ssim_threshold: float = 0.85   # SSIM 相似度阈值（仅边界 case）
    thumbnail_size: List[int] = Field(default_factory=lambda: [64, 36])


class CaptureConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = 15
    max_width: int = 1600
    quality: int = 75
    save_raw_screenshot_days: int = 14
    # 多屏
    per_monitor: bool = True
    monitors: List[int] = Field(default_factory=list)  # 空=全部
    # 高分辨率
    vlm_max_width: int = 2048
    hash_max_width: int = 640
    # 去重
    dedup: DedupConfig = Field(default_factory=DedupConfig)


class PrivacyConfig(BaseModel):
    local_only: bool = True
    excluded_apps: List[str] = Field(default_factory=lambda: [
        "1Password", "Bitwarden", "KeePass",
        "WeChat", "微信", "Telegram", "Signal",
        "Banking", "支付宝", "微信支付",
        "Windows Security", "Credential Manager",
    ])
    excluded_domains: List[str] = Field(default_factory=lambda: [
        "bank", "paypal", "alipay", "password", "login", "auth", "account",
    ])
    redact_keywords: List[str] = Field(default_factory=lambda: [
        "password", "token", "api_key", "身份证", "银行卡",
    ])


class VLMConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:1234/v1"
    api_key: str = "lm-studio"
    model: str = "local-vlm-model"
    max_tokens: int = 1024
    temperature: float = 0.1
    timeout: int = 60       # 秒
    retry_count: int = 2


class EmbeddingConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:1234/v1"
    api_key: str = "lm-studio"
    model: str = "local-embedding-model"
    timeout: int = 30       # 秒
    retry_count: int = 2


class ModelsConfig(BaseModel):
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class RetrievalConfig(BaseModel):
    top_k: int = 8
    use_vector: bool = True
    use_fts_fallback: bool = True


# ── 主配置 ──────────────────────────────────────────────────────

class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


# ── 加载函数 ────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> AppConfig:
    """加载配置：默认值 → config.yaml → .env.local → 环境变量。

    环境变量前缀：
      HCM_VLM_BASE_URL, HCM_VLM_API_KEY, HCM_VLM_MODEL
      HCM_EMBEDDING_BASE_URL, HCM_EMBEDDING_API_KEY, HCM_EMBEDDING_MODEL
      HCM_SERVER_PORT, HCM_CAPTURE_INTERVAL_SECONDS 等
    """
    path = config_path or CONFIG_PATH
    data: dict = {}

    # 从 YAML 文件加载
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # 从 .env.local 加载
    env_local = PROJECT_ROOT / ".env.local"
    if env_local.exists():
        try:
            from dotenv import dotenv_values
            env_values = dotenv_values(env_local)
            for k, v in env_values.items():
                os.environ.setdefault(k, v)
        except ImportError:
            # 手动解析 .env.local
            with open(env_local, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    # HCM_ 前缀的专用映射
    _hcm_mapping = {
        "HCM_VLM_BASE_URL": ("models", "vlm", "base_url"),
        "HCM_VLM_API_KEY": ("models", "vlm", "api_key"),
        "HCM_VLM_MODEL": ("models", "vlm", "model"),
        "HCM_VLM_ENABLED": ("models", "vlm", "enabled"),
        "HCM_EMBEDDING_BASE_URL": ("models", "embedding", "base_url"),
        "HCM_EMBEDDING_API_KEY": ("models", "embedding", "api_key"),
        "HCM_EMBEDDING_MODEL": ("models", "embedding", "model"),
        "HCM_EMBEDDING_ENABLED": ("models", "embedding", "enabled"),
        "HCM_SERVER_PORT": ("server", "port"),
        "HCM_SERVER_HOST": ("server", "host"),
        "HCM_CAPTURE_INTERVAL": ("capture", "interval_seconds"),
        "HCM_CAPTURE_ENABLED": ("capture", "enabled"),
    }
    for env_key, path_tuple in _hcm_mapping.items():
        value = os.environ.get(env_key)
        if value is not None:
            target = data
            for part in path_tuple[:-1]:
                target = target.setdefault(part, {})
            # 类型转换
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            target[path_tuple[-1]] = value

    # HERMES_ 前缀兼容（旧版）
    env_prefix = "HERMES_"
    for key, value in os.environ.items():
        if not key.startswith(env_prefix):
            continue
        parts = key[len(env_prefix):].lower().split("_")
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        target[parts[-1]] = value

    return AppConfig(**data)


# ── 初始化配置文件 ──────────────────────────────────────────────

def init_config(config_path: Path | None = None) -> AppConfig:
    """如果 config.yaml 不存在，从 config.example.yaml 复制创建。"""
    path = config_path or CONFIG_PATH
    if not path.exists():
        example = PROJECT_ROOT / "config.example.yaml"
        if example.exists():
            import shutil
            shutil.copy2(example, path)
        else:
            # 写入默认配置
            cfg = AppConfig()
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(cfg.model_dump(), f, default_flow_style=False, allow_unicode=True)
    return load_config(path)
