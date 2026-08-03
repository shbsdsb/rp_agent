import pytest

from rp_agent.api.models import ApiConnection, mask_key


def _conn(**overrides):
    params = dict(
        name="demo",
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="gpt-4o",
    )
    params.update(overrides)
    return ApiConnection(**params)


def test_default_timeout():
    assert _conn().timeout == 120.0


def test_validate_ok():
    _conn().validate()  # 不抛错


@pytest.mark.parametrize(
    "overrides",
    [{"name": ""}, {"base_url": "ftp://x"}, {"timeout": 0}],
)
def test_validate_invalid(overrides):
    with pytest.raises(ValueError):
        _conn(**overrides).validate()


def test_validate_allows_empty_model():
    _conn(model="").validate()  # model 可选,允许为空


def test_new_fields_defaults():
    conn = _conn()
    assert conn.models_endpoint == "/models"
    assert conn.last_tested == ""


def test_mask_key():
    assert mask_key("sk-1234567890abcdef") == "sk-1****cdef"
    assert mask_key("short") == "****"  # 长度 <= 8
    assert mask_key("") == "****"
