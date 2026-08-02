import pytest

from rp_agent.api.models import ApiConnection


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
    assert _conn().timeout == 30.0


def test_validate_ok():
    _conn().validate()  # 不抛错


@pytest.mark.parametrize(
    "overrides",
    [{"name": ""}, {"base_url": "ftp://x"}, {"model": ""}, {"timeout": 0}],
)
def test_validate_invalid(overrides):
    with pytest.raises(ValueError):
        _conn(**overrides).validate()
