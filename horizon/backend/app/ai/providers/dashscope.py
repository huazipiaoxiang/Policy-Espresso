"""阿里云百炼 DashScope Provider（OpenAI 兼容端点）。密钥只走环境变量。"""
from __future__ import annotations

from app.core.config import get_settings
from app.ai.providers.openai_compat import OpenAICompatProvider


class DashScopeProvider(OpenAICompatProvider):
    name = "dashscope"

    def __init__(self, *, api_key: str, base_url: str):
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        # 默认模型取 plus 档；chain 层按任务经 settings.model_for_task 指定档位
        super().__init__(base_url=base_url, api_key=api_key, default_model=get_settings().llm_model_plus)
