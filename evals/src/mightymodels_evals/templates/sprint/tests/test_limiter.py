import pytest
from src.limiter import validate_limit

def test_validate():
    assert validate_limit(1) is True
    assert validate_limit(30) is True
    with pytest.raises(ValueError):
        validate_limit(31)
