# -*- coding: utf-8 -*-
"""
配置持久化层

支持 JSON 配置文件持久化，与 .env 文件兼容。
启动时自动加载 JSON 配置到环境变量。
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigStorage:
    """JSON 配置持久化管理器"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.models_file = self.config_dir / "models.json"
        self.settings_file = self.config_dir / "settings.json"
        self.data_sources_file = self.config_dir / "data_sources.json"
        self._cache = {}

    def initialize(self):
        """初始化配置目录和默认文件"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 创建默认配置文件（如果不存在）
        if not self.models_file.exists():
            self._save_json(self.models_file, self._default_models())

        if not self.settings_file.exists():
            self._save_json(self.settings_file, self._default_settings())

        if not self.data_sources_file.exists():
            self._save_json(self.data_sources_file, self._default_data_sources())

    def _save_json(self, file_path: Path, data: Any):
        """安全保存 JSON 文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._cache[file_path.name] = data
            logger.debug(f"配置已保存：{file_path}")
        except Exception as e:
            logger.error(f"保存配置文件失败 {file_path}: {e}")

    def _load_json(self, file_path: Path, default: Any = None) -> Any:
        """加载 JSON 文件，支持缓存"""
        if file_path.name in self._cache:
            return self._cache[file_path.name]

        if not file_path.exists():
            return default or {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._cache[file_path.name] = data
            return data
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误 {file_path}: {e}")
            return default or {}
        except Exception as e:
            logger.error(f"加载配置文件失败 {file_path}: {e}")
            return default or {}

    # ==================== LLM 模型配置 ====================

    def _default_models(self) -> List[Dict[str, Any]]:
        """默认模型配置"""
        return [
            {
                "provider": "openai",
                "model_name": "gpt-4o-mini",
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "enabled": False,
                "description": "OpenAI GPT-4o Mini（需配置 API Key）"
            },
            {
                "provider": "dashscope",
                "model_name": "qwen-turbo",
                "api_key": "",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "enabled": True,
                "description": "阿里云通义千问 Turbo"
            }
        ]

    def get_models(self) -> List[Dict[str, Any]]:
        """获取 LLM 模型配置列表"""
        return self._load_json(self.models_file, self._default_models())

    def save_models(self, models: List[Dict[str, Any]]) -> bool:
        """保存 LLM 模型配置"""
        try:
            self._save_json(self.models_file, models)
            return True
        except Exception as e:
            logger.error(f"保存模型配置失败：{e}")
            return False

    def get_enabled_models(self) -> List[Dict[str, Any]]:
        """获取已启用的模型列表"""
        models = self.get_models()
        return [m for m in models if m.get("enabled", False)]

    # ==================== 系统设置 ====================

    def _default_settings(self) -> Dict[str, Any]:
        """默认系统设置"""
        return {}

    def get_settings(self) -> Dict[str, Any]:
        """获取系统设置"""
        return self._load_json(self.settings_file, self._default_settings())

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """保存系统设置（合并更新）"""
        try:
            current = self.get_settings()
            current.update(settings)
            self._save_json(self.settings_file, current)
            return True
        except Exception as e:
            logger.error(f"保存系统设置失败：{e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取单个设置项"""
        settings = self.get_settings()
        return settings.get(key, default)

    # ==================== 数据源配置 ====================

    def _default_data_sources(self) -> List[Dict[str, Any]]:
        """默认数据源配置"""
        return [
            {
                "name": "AKShare",
                "type": "akshare",
                "enabled": True,
                "priority": 1,
                "retry_times": 3,
                "timeout": 30,
                "description": "AKShare 开源金融数据接口"
            },
            {
                "name": "yfinance",
                "type": "yfinance",
                "enabled": True,
                "priority": 2,
                "retry_times": 2,
                "timeout": 15,
                "description": "Yahoo Finance 数据源"
            },
            {
                "name": "EFinance",
                "type": "efinance",
                "enabled": True,
                "priority": 3,
                "retry_times": 2,
                "timeout": 15,
                "description": "东方财富数据接口"
            },
            {
                "name": "Tushare",
                "type": "tushare",
                "enabled": False,
                "priority": 4,
                "retry_times": 2,
                "timeout": 15,
                "description": "Tushare 专业金融数据接口（需 Token）"
            }
        ]

    def get_data_sources(self) -> List[Dict[str, Any]]:
        """获取数据源配置（按优先级排序）"""
        sources = self._load_json(self.data_sources_file, self._default_data_sources())
        # 按优先级排序（数字越小优先级越高）
        sources.sort(key=lambda x: x.get("priority", 999))
        return sources

    def get_enabled_sources(self) -> List[Dict[str, Any]]:
        """获取已启用的数据源列表"""
        sources = self.get_data_sources()
        return [s for s in sources if s.get("enabled", False)]

    def save_data_sources(self, sources: List[Dict[str, Any]]) -> bool:
        """保存数据源配置"""
        try:
            self._save_json(self.data_sources_file, sources)
            return True
        except Exception as e:
            logger.error(f"保存数据源配置失败：{e}")
            return False

    # ==================== 环境变量加载 ====================

    def load_to_env(self):
        """将 JSON 配置加载到环境变量（.env 兜底）"""
        settings = self.get_settings()

        # 映射关系到环境变量
        env_mapping = {}

        for key, value in env_mapping.items():
            if value is not None and key not in os.environ:
                os.environ[key] = str(value)
                logger.debug(f"从 JSON 配置加载环境变量：{key}={value}")

        logger.info("JSON 配置已加载到环境变量")


# 全局实例
config_storage = ConfigStorage()
