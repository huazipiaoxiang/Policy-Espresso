"""全局配置。所有配置项必须在 .env.example 中有对应条目。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./horizon.db"

    llm_provider: str = "mock"  # mock | ollama | dashscope
    llm_model_flash: str = "qwen-flash"
    llm_model_plus: str = "qwen-plus"
    llm_model_max: str = "qwen-max"
    llm_model_long: str = "qwen-long"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:7b-instruct"

    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = "dev-local-key"
    tz_display: str = "Asia/Hong_Kong"
    log_level: str = "INFO"
    storage_dir: str = "./storage"

    crawl_user_agent: str = "HORIZON-PolicyMonitor/0.1 (+policy-research; contact@example.com)"
    crawl_max_rps_per_domain: float = 1.0
    crawl_respect_robots: bool = True

    # ===== Phase 5 云端 =====
    storage_backend: str = "local"  # local | oss
    oss_bucket: str = ""
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    job_trigger_token: str = ""  # FC 定时触发 /internal/jobs/* 的签名令牌
    crawl_max_attachments_per_doc: int = 3  # 每文档最多解析的 PDF 附件数（06 §5.6）
    crawl_max_items_per_source: int = 0  # 单源单轮最多抓取条数；0=不限制（测试/调试时限量的开关）

    notify_email_webhook: str = ""
    notify_wecom_webhook: str = ""
    notify_feishu_webhook: str = ""

    def model_for_task(self, task: str) -> str:
        """模型分层路由：分类 flash / 抽取 plus / 分析 max / 长文 long。"""
        tier = {
            "classify": self.llm_model_flash,
            "extract": self.llm_model_plus,
            "scope": self.llm_model_plus,
            "impact": self.llm_model_max,
            "case": self.llm_model_plus,
            "studio": self.llm_model_max,
        }.get(task, self.llm_model_plus)
        return tier


@lru_cache
def get_settings() -> Settings:
    return Settings()
