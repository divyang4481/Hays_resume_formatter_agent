from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    cloud_provider: str = "aws"
    runtime_mode: str = "aws"
    processing_mode: str = "async"
    queue_provider: str = "sqs"
    storage_provider: str = "s3"
    agent_provider: str = "python_orchestrated"
    knowledge_provider: str = "bedrock_kb"
    llm_backend: str = "aws_bedrock"

    aws_region: str = "ap-south-1"
    aws_profile: str = "default"

    s3_bucket: str = "hays-resume-agent-dev"
    s3_bucket_input: str = ""
    s3_bucket_output: str = ""
    sqs_template_analysis_queue_url: str = ""
    sqs_resume_format_queue_url: str = ""
    sqs_processing_queue_url: str = ""
    use_aws_services: bool = False
    sqs_wait_time_seconds: int = 10
    sqs_visibility_timeout_seconds: int = 30

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/resume_agent"

    llm_provider: str = "bedrock"
    llm_model_fast: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
    llm_model_strong: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    llm_api_key: str = ""
    bedrock_agent_id: str = ""
    bedrock_agent_alias_id: str = ""
    bedrock_kb_id: str = ""

    enable_auth: bool = False

    # Bedrock Fallback & Tokens configuration
    bedrock_fallback_model_id: str = "meta.llama3-70b-instruct-v1:0"
    bedrock_max_output_tokens_template_analysis: int = 32768
    bedrock_temperature_template_analysis: float = 0.0
    bedrock_max_output_tokens_data_mapping: int = 8192
    bedrock_temperature_data_mapping: float = 0.0
    bedrock_max_output_tokens_default: int = 8192
    bedrock_temperature_default: float = 0.1

    template_analysis_model_profile: str = "balanced"
    template_analysis_models: dict = {
        "evidence_normalizer": {
            "provider": "aws_bedrock",
            "model_id": "qwen.qwen3-235b-a22b-2507-v1:0",
            "temperature": 0.0,
            "max_tokens": 8192
        },
        "manifest_generator": {
            "provider": "aws_bedrock",
            "model_id": "qwen.qwen3-235b-a22b-2507-v1:0",
            "temperature": 0.0,
            "max_tokens": 32768
        },
        "manifest_repair": {
            "provider": "aws_bedrock",
            "model_id": "qwen.qwen3-235b-a22b-2507-v1:0",
            "temperature": 0.0,
            "max_tokens": 32768
        },
        "manifest_critic": {
            "provider": "aws_bedrock",
            "model_id": "meta.llama3-70b-instruct-v1:0",
            "temperature": 0.0,
            "max_tokens": 6000,
            "enabled": False
        }
    }

    local_storage_path: str = "./data"
    vector_search_enabled: bool = False
    template_selector_mode: str = "legacy"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
