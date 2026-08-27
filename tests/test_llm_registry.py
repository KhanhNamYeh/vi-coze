"""Kiểm chứng llm/registry — đọc .env và tách chuỗi "<provider>:<model>".

Không gọi mạng: chỉ kiểm phần thuần logic. Phần "model có sống không" nằm ở
`python -m src.branch_sql.online.llm`, cần khoá thật nên không đưa vào pytest.
"""

from __future__ import annotations

import pytest

from src.branch_sql.online.llm import registry


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "\n"
        "GOOGLE_API_KEY=key-google\n"
        'OPENAI_API_KEY="key-openai"\n'
        "OPENAI_MODELS=gpt-5.4, gpt-5.6-luna ,\n"
        "GOOGLE_MODELS=gemini-3.5-flash-lite\n"
        "NVIDIA_API_KEY=\n"
        "khong_phai_gan_gia_tri\n",
        encoding="utf-8",
    )
    # load_env dùng setdefault nên biến còn sót từ .env thật (hoặc từ test khác
    # chạy trước trong cùng process) sẽ đè lên .env giả -> xoá sạch.
    monkeypatch.delenv("SQL_LLM", raising=False)
    for key_var, models_var, base_var in registry.PROVIDERS.values():
        for var in (key_var, models_var, base_var):
            if var:
                monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(registry, "ENV_FILE", path)
    return path


def test_load_env_bo_qua_comment_va_dong_rong(env_file):
    loaded = registry.load_env()
    assert loaded["GOOGLE_API_KEY"] == "key-google"
    # Giá trị có nháy kép phải được bóc; dòng thiếu "=" bị bỏ qua.
    assert loaded["OPENAI_API_KEY"] == "key-openai"
    assert "khong_phai_gan_gia_tri" not in loaded
    # Biến khai báo rỗng không được nạp — coi như chưa cấu hình.
    assert "NVIDIA_API_KEY" not in loaded


def test_catalog_chi_lay_provider_co_khoa(env_file):
    assert registry.catalog() == [
        ("google", "gemini-3.5-flash-lite"),
        ("openai", "gpt-5.4"),
        ("openai", "gpt-5.6-luna"),
    ]


def test_catalog_giu_thu_tu_provider_trong_PROVIDERS(env_file):
    # google đứng trước openai trong PROVIDERS nên phải ra trước, dù .env khai
    # OPENAI_MODELS ở dòng trên.
    assert [p for p, _ in registry.catalog()][0] == "google"


@pytest.mark.parametrize("spec", ["gpt-5.4", "", "khong-co-dau-hai-cham"])
def test_build_model_bat_spec_sai_dinh_dang(env_file, spec):
    with pytest.raises(ValueError, match="provider"):
        registry.build_model(spec)


def test_build_model_bat_provider_la(env_file):
    with pytest.raises(ValueError, match="lạ"):
        registry.build_model("anthropic:claude-sonnet-4-5")


def test_build_model_bao_thieu_khoa(env_file):
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        registry.build_model("nvidia:nvidia/nemotron-3.5-lightning-30b-a3b")


def test_build_model_tach_dung_model_id_co_dau_hai_cham(env_file, monkeypatch):
    """OpenRouter dùng id kiểu `nvidia/nemotron-3.5-lightning:free` — dấu ":"
    thứ hai thuộc về tên model, không phải phân cách provider."""
    ghi = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            ghi.update(kwargs)

    monkeypatch.setenv("OPENROUTER_API_KEY", "key-or")
    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)
    registry.build_model("openrouter:nvidia/nemotron-3.5-lightning:free")
    assert ghi["model"] == "nvidia/nemotron-3.5-lightning:free"


def test_build_model_openai_mac_dinh_dung_responses_api(env_file, monkeypatch):
    """gpt-5.6-* từ chối function tool trên /v1/chat/completions."""
    ghi = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            ghi.update(kwargs)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)
    registry.build_model("openai:gpt-5.6-luna")
    assert ghi["use_responses_api"] is True
    # Nhưng gọi thẳng vẫn tắt được.
    registry.build_model("openai:gpt-5.6-luna", use_responses_api=False)
    assert ghi["use_responses_api"] is False


def test_build_model_khong_tu_them_temperature(env_file, monkeypatch):
    """Model reasoning trả 400 nếu nhận temperature — factory phải im lặng."""
    ghi = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            ghi.update(kwargs)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)
    registry.build_model("openai:gpt-5.4")
    assert "temperature" not in ghi and "top_p" not in ghi
