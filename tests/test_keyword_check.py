"""핵심어 대조 도구 시험 (가짜 후보로만, 봉인 파일을 열지 않음)."""
from __future__ import annotations

from tools.keyword_check import count_hits, keywords

FAKE = [
    {"id": "X1", "name": "가짜 사례 하나 (fake_column 사용)", "how_to_inject": "features.fake_column 추가"},
    {"id": "X2", "name": "다른 가짜 사례", "how_to_inject": "split.key 변경"},
]


def test_keywords_ascii_and_hangul_pairs():
    kw = keywords(FAKE)
    assert kw["fake_column"] == {"X1"}
    assert kw["features.fake_column"] == {"X1"}
    assert kw["split.key"] == {"X2"}
    assert kw["가짜 사례"] == {"X1", "X2"}
    assert "사례" not in kw  # 한 어절만으로는 핵심어가 아니다


def test_count_hits_uses_word_boundaries():
    kw = keywords(FAKE)
    hits = count_hits(kw, "SPLIT.KEY 와 my_fake_column, 그리고 가짜 사례 둘. 가짜 사례.")
    assert hits["split.key"] == 1
    assert "fake_column" not in hits  # my_fake_column 안의 부분 문자열은 세지 않는다
    assert hits["가짜 사례"] == 2
