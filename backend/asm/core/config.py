from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    volc_tts_app_key: str = ""
    volc_tts_access_key: str = ""
    volc_tts_api_key: str = ""
    volc_tts_resource_id: str = "seed-tts-2.0"
    volc_tts_speaker: str = ""

    def volc_tts_ready(self) -> bool:
        if not self.volc_tts_speaker:
            return False
        if self.volc_tts_api_key:
            return True
        return bool(self.volc_tts_access_key and self.volc_tts_app_key)

    asm_host: str = "127.0.0.1"
    asm_port: int = 8765

    speculate_after_ms: int = 300
    commit_after_ms: int = 700
    barge_in_confirm_ms: int = 300
    barge_in_min_chars: int = 2
    barge_in_holdoff_ms: int = 250
    partial_hang_ms: int = 1200
    recall_deadline_ms: int = 400
    first_min_chars: int = 4
    later_min_chars: int = 8
    first_token_timeout_s: float = 5.0
    context_window_tokens: int = 1_000_000
    context_reserve_ratio: float = 0.15

    prompts_dir: str = "prompts"
    impulse_enabled: bool = True
    idle_companion_s: float = 180
    memory_dir: str = "data/memory"
