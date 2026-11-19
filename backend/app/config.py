from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "HyperCortex RAG API"
    app_version: str = "1.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    data_dir: Path = BACKEND_DIR / "data"
    max_upload_mb: int = 200
    max_files_per_job: int = 20
    ingest_workers: int = 2

    chunk_size: int = 800
    chunk_overlap: int = 120
    min_chunk_chars: int = 30
    dense_top_k: int = 30
    bm25_top_k: int = 30
    rerank_enabled: bool = True
    rerank_model: str = ""
    rerank_top_k: int = 8
    min_relevance_score: float = 0.18
    max_chunks_per_document: int = 2
    max_context_chars: int = 8000

    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    embedding_query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_model: str = "text-embedding-3-small"

    vector_store: str = "chroma"

    llm_provider: str = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1200

    ocr_enabled: bool = False
    allowed_extensions: str = (
        ".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.markdown,.html,.htm,.json,.mhtml"
    )
    url_timeout_seconds: int = 20
    allow_private_urls: bool = False

    # Wiki / 深度研究
    wiki_enabled: bool = True
    # none | auto | duckduckgo | tavily | serpapi | searxng
    search_provider: str = "auto"
    tavily_api_key: str = ""
    serpapi_api_key: str = ""
    searxng_url: str = "http://127.0.0.1:8080"

    @property
    def data_path(self) -> Path:
        path = self.data_dir
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path

    @property
    def db_path(self) -> Path:
        return self.data_path / "hypercortex.db"

    @property
    def uploads_path(self) -> Path:
        return self.data_path / "uploads"

    @property
    def chroma_path(self) -> Path:
        return self.data_path / "chroma"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {
            extension.strip().lower()
            for extension in self.allowed_extensions.split(",")
            if extension.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
