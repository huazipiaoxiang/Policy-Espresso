"""全局配置。所有配置项必须在 .env.example 中有对应条目。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./horizon.db"
    scheduler_timezone: str = "Asia/Hong_Kong"
    scheduler_heartbeat_cron: str = "0 8 * * mon"

    llm_provider: str = "mock"  # mock | ollama | dashscope
    # 未接入真实 LLM 时改用离线规则派生政策内容，避免 mock 样例把每篇文档写成同一份内容
    llm_offline_rules: bool = False
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
    # 前端跨域白名单，逗号分隔；本地换端口（如 3002）在这里加，不用改代码
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002"
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

    # ===== Chat Agent（LLM 自主检索循环） =====
    # 关闭时 /chat 走原 grounded 路径，行为与改造前完全一致（灰度回退开关）。
    chat_agent_enabled: bool = False
    chat_max_tool_rounds: int = 3          # Executor 最多轮次（每轮 1 次 LLM + 若干工具调用）
    chat_evidence_max: int = 8             # 累积证据池上限（沿用原 MAX_EVIDENCE）
    chat_max_invalid_calls: int = 2        # 连续无效调用（空结果/不可解析）达到此数即早停
    chat_planner_enabled: bool = True      # 关闭时跳过 Planner，直接用原问题进 Executor

    # ===== 检索层（向量 + 词法融合，见 app/search/README 约定） =====
    search_vector_enabled: bool = True     # 总开关；索引为空/无 numpy/嵌入失败时静默降级
    search_embedding_provider: str = ""    # 空=跟随 llm_provider；可显式 dashscope|ollama|mock
    search_embedding_model: str = ""       # 空=按 provider 取默认
    search_chunk_size: int = 800
    search_chunk_overlap: int = 120
    search_chunk_max_per_doc: int = 20
    search_vector_top_k: int = 8
    search_rrf_k: int = 60

    def model_for_task(self, task: str) -> str:
        """模型分层路由：分类 flash / 抽取 plus / 分析 max / 长文 long。"""
        tier = {
            "classify": self.llm_model_flash,
            "extract": self.llm_model_plus,
            "scope": self.llm_model_plus,
            "impact": self.llm_model_max,
            "case": self.llm_model_plus,
            "studio": self.llm_model_max,
            # Chat：Planner 只做指代消解与查询改写，走最便宜的 flash；答复用 plus。
            "chat_plan": self.llm_model_flash,
            "chat_answer": self.llm_model_plus,
        }.get(task, self.llm_model_plus)
        return tier


@lru_cache
def get_settings() -> Settings:
    return Settings()
