import pytest

from synth.generate_v2 import generate


@pytest.fixture(scope="session")
def small_tables():
    """사람 300명 v2 합성 데이터 17개 테이블 (빠른 시험용)."""
    return generate("main", seed=7, n_persons=300).tables
