from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pandas as pd


RIASEC_ORDER = ["R", "I", "A", "S", "E", "C"]
RAW_SCORE_KEY = "원점수"
T_SCORE_KEY = "T점수"
RIASEC_LABELS = ["현실형", "탐구형", "예술형", "사회형", "진취형", "관습형"]
T_SCORE_COLUMNS = {
    "현실형": "현실형(R) T",
    "탐구형": "탐구형(I) T",
    "예술형": "예술형(A) T",
    "사회형": "사회형(S) T",
    "진취형": "진취형(E) T",
    "관습형": "관습형(C) T",
}
RAW_CODE_MAP = {
    "현실형": "R",
    "탐구형": "I",
    "예술형": "A",
    "사회형": "S",
    "진취형": "E",
    "관습형": "C",
}
CODE_TO_THEME = {
    "R": "실행형 문제 해결",
    "I": "분석과 탐구",
    "A": "창의적 기획",
    "S": "협업과 지원",
    "E": "주도와 설득",
    "C": "정리와 시스템 운영",
}

PDF_SCORE_PATTERN = re.compile(
    r"직업\s*흥미\s*유형별\s*점수.*?"
    r"현실형.*?탐구형.*?예술형.*?사회형.*?진취형.*?관습형.*?"
    r"원\s*점\s*수\s*([0-9\s]+?)\s*표준점수\s*([0-9\s]+)",
    re.S,
)

JOB_SELECT_SQL = """
SELECT
    id,
    JK_L_category,
    JK_M_category,
    similar_job_name,
    top3,
    realistic_score,
    investigative_score,
    artistic_score,
    social_score,
    enterprising_score,
    conventional_score,
    major_required,
    job_information
FROM JK_job
"""

JOB_FRAME_COLUMNS = [
    "id",
    "대분류",
    "중분류",
    "매핑 O*NET 직업명",
    "Top3",
    "참고 유사직업(1차)",
    "전공필수",
    "직무정보",
    *T_SCORE_COLUMNS.values(),
]


class JobCatalogError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise JobCatalogError(f"MySQL 환경변수 {name}가 설정되어 있지 않습니다.")
    return value


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        return int(raw_value)
    except ValueError as exc:
        raise JobCatalogError(f"MySQL 환경변수 {name}는 정수여야 합니다.") from exc


def get_db_connection():
    try:
        import pymysql
    except ImportError as exc:
        raise JobCatalogError("pymysql이 설치되어 있지 않습니다. requirements.txt 설치를 확인해주세요.") from exc

    try:
        connection_kwargs = {
            "user": _required_env("MYSQL_USER"),
            "password": _required_env("MYSQL_PASSWORD"),
            "database": _required_env("MYSQL_DATABASE"),
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
            "connect_timeout": _int_env("MYSQL_CONNECT_TIMEOUT", 5),
        }

        instance_connection_name = os.getenv("INSTANCE_CONNECTION_NAME", "").strip()
        if instance_connection_name:
            return pymysql.connect(
                unix_socket=f"/cloudsql/{instance_connection_name}",
                **connection_kwargs,
            )

        return pymysql.connect(
            host=_required_env("MYSQL_HOST"),
            port=_int_env("MYSQL_PORT", 3306),
            **connection_kwargs,
        )
    except JobCatalogError:
        raise
    except Exception as exc:
        raise JobCatalogError(f"MySQL 연결에 실패했습니다: {exc}") from exc


def query_job_rows(sql: str, params: tuple = ()) -> list[dict]:
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    except Exception as exc:
        raise JobCatalogError(f"JK_job 조회 중 오류가 발생했습니다: {exc}") from exc
    finally:
        connection.close()


def normalize_db_job(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "대분류": row.get("JK_L_category"),
        "중분류": row.get("JK_M_category"),
        "매핑 O*NET 직업명": row.get("similar_job_name"),
        "Top3": row.get("top3"),
        "참고 유사직업(1차)": "",
        "전공필수": row.get("major_required"),
        "직무정보": row.get("job_information"),
        "현실형(R) T": row.get("realistic_score"),
        "탐구형(I) T": row.get("investigative_score"),
        "예술형(A) T": row.get("artistic_score"),
        "사회형(S) T": row.get("social_score"),
        "진취형(E) T": row.get("enterprising_score"),
        "관습형(C) T": row.get("conventional_score"),
    }


def serialize_db_job(row: dict, rank: int | None = None) -> dict:
    return serialize_job(pd.Series(normalize_db_job(row)), rank=rank)


def extract_scores_from_pdf(pdf_path: str | Path) -> dict[str, dict[str, int]]:
    doc = fitz.open(pdf_path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()

    match = PDF_SCORE_PATTERN.search(text)
    if not match:
        raise ValueError("PDF에서 RIASEC 점수를 찾지 못했습니다.")

    raw_scores = list(map(int, match.group(1).split()))
    t_scores = list(map(int, match.group(2).split()))
    if len(raw_scores) != 6 or len(t_scores) != 6:
        raise ValueError("PDF에서 추출한 RIASEC 점수 개수가 올바르지 않습니다.")

    return {
        label: {RAW_SCORE_KEY: raw, T_SCORE_KEY: t_score}
        for label, raw, t_score in zip(RIASEC_LABELS, raw_scores, t_scores)
    }


def load_jobs_dataframe(file_path: str | Path | None = None) -> pd.DataFrame:
    if file_path is not None:
        raise JobCatalogError("CSV file_path 로딩은 더 이상 지원하지 않습니다. JK_job DB 테이블을 사용해주세요.")

    rows = query_job_rows(f"{JOB_SELECT_SQL} ORDER BY id")
    records = [normalize_db_job(row) for row in rows]
    return pd.DataFrame(records, columns=JOB_FRAME_COLUMNS)


def parse_top3_codes(top3_value) -> list[str]:
    if pd.isna(top3_value):
        return []

    extracted = [ch for ch in str(top3_value).upper() if ch in RIASEC_ORDER]
    seen: set[str] = set()
    result: list[str] = []
    for code in extracted:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result[:3]


def build_job_tags(row: pd.Series) -> list[str]:
    tags = [clean_text(row.get("대분류")), clean_text(row.get("중분류"))]
    tags.extend(CODE_TO_THEME[code] for code in parse_top3_codes(row.get("Top3")))
    deduped: list[str] = []
    for tag in tags:
        if tag and tag not in deduped:
            deduped.append(tag)
    return deduped[:5]


def clean_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def safe_float(value, default=None):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def serialize_job_id(value, fallback) -> int | str:
    if value is None:
        return str(fallback)
    try:
        if pd.isna(value):
            return str(fallback)
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def summarize_text(text: str, max_length: int = 90) -> str:
    text = re.sub(r"\s+", " ", clean_text(text))
    if not text:
        return ""

    sentence_match = re.match(r"(.+?[.!?。！？])\s*", text)
    if sentence_match:
        sentence = sentence_match.group(1).strip()
        if sentence != text:
            return sentence if len(sentence) <= max_length else f"{sentence[: max_length - 1].rstrip()}…"

    if len(text) <= max_length:
        return text

    return f"{text[: max_length - 1].rstrip()}…"


def extract_job_definition_text(job_information: str) -> str:
    text = clean_text(job_information)
    if not text:
        return ""

    section_match = re.search(
        r"(?:^|\n)\s*\d+\.\s*직무\s*정의\s*[:：]\s*(.*?)(?=\n\s*\d+\.\s*[^:\n：]+[:：]|\Z)",
        text,
        re.S,
    )
    if section_match:
        return re.sub(r"\s+", " ", section_match.group(1)).strip()

    text = re.sub(r"^\s*\d+\.\s*직무\s*정의\s*[:：]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def build_job_full_description(row: pd.Series) -> str:
    information = clean_text(row.get("직무정보"))
    if information:
        return information

    related = clean_text(row.get("참고 유사직업(1차)", ""))
    top3 = ", ".join(parse_top3_codes(row.get("Top3")))
    category = clean_text(row.get("대분류"))
    title = clean_text(row.get("중분류"))
    onet_title = clean_text(row.get("매핑 O*NET 직업명"))
    parts = [
        f"{title}는 {category} 분야에서 활동하는 직무입니다.",
        f"O*NET 기준 연관 직무는 {onet_title}입니다.",
    ]
    if top3:
        parts.append(f"흥미 코드는 {top3} 축이 강한 역할로 해석할 수 있습니다.")
    if related:
        parts.append(f"유사 직무 예시로는 {related} 등이 있습니다.")
    return " ".join(parts)


def serialize_job(row: pd.Series, rank: int | None = None) -> dict:
    scores = {label: safe_float(row.get(column), 0.0) for label, column in T_SCORE_COLUMNS.items()}
    full_description = build_job_full_description(row)
    summary = summarize_text(extract_job_definition_text(full_description) or full_description)
    return {
        "id": serialize_job_id(row.get("id"), row.name),
        "rank": rank,
        "category": clean_text(row.get("대분류")),
        "title": clean_text(row.get("중분류")),
        "onet_title": clean_text(row.get("매핑 O*NET 직업명")),
        "top3": clean_text(row.get("Top3")),
        "related_jobs": clean_text(row.get("참고 유사직업(1차)")),
        "major_required": clean_text(row.get("전공필수")),
        "description": summary,
        "information_summary": summary,
        "job_information": full_description,
        "tags": build_job_tags(row),
        "scores": scores,
        "final_score": safe_float(row.get("최종유사도"), None),
    }


def recommend_jobs_for_user_profile(
    user_scores: dict[str, dict[str, int]],
    file_path: str | Path | None = None,
    top_n: int = 20,
):
    df = load_jobs_dataframe(file_path)

    user_profile = {
        T_SCORE_COLUMNS[label]: scores[T_SCORE_KEY]
        for label, scores in user_scores.items()
    }
    user_raw_profile = {
        RAW_CODE_MAP[label]: scores[RAW_SCORE_KEY]
        for label, scores in user_scores.items()
    }

    score_cols = list(user_profile.keys())
    user_vec = np.array([user_profile[col] for col in score_cols], dtype=float)
    user_raw_top3 = sorted(
        user_raw_profile,
        key=lambda code: (-user_raw_profile[code], RIASEC_ORDER.index(code)),
    )[:3]

    work_df = df.copy()
    for col in score_cols:
        work_df[col] = pd.to_numeric(work_df[col], errors="coerce")

    work_df = work_df.dropna(subset=score_cols).reset_index(drop=True)
    job_matrix = work_df[score_cols].to_numpy(dtype=float)

    def cosine_similarity_matrix(X: np.ndarray, y: np.ndarray) -> np.ndarray:
        x_norm = np.linalg.norm(X, axis=1)
        y_norm = np.linalg.norm(y)
        denom = np.where((x_norm * y_norm) == 0, np.nan, x_norm * y_norm)
        cos = (X @ y) / denom
        return np.nan_to_num(cos, nan=0.0)

    def euclidean_distance_matrix(X: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.linalg.norm(X - y, axis=1)

    def distance_to_similarity(dist: np.ndarray) -> np.ndarray:
        return 1 / (1 + dist)

    def raw_top3_bonus(job_top3: list[str], user_top3: list[str]) -> float:
        if not job_top3 or len(user_top3) < 3:
            return 0.0

        score = 0.0
        user_weights = {user_top3[0]: 3, user_top3[1]: 2, user_top3[2]: 1}
        for i, code in enumerate(job_top3):
            if code in user_weights:
                score += user_weights[code] * (3 - i)
        return score / 14

    cos_sim = cosine_similarity_matrix(job_matrix, user_vec)
    dist = euclidean_distance_matrix(job_matrix, user_vec)
    dist_sim = distance_to_similarity(dist)
    t_final_sim = 0.75 * cos_sim + 0.25 * dist_sim
    top3_bonus_arr = np.array(
        [
            raw_top3_bonus(parse_top3_codes(row["Top3"]), user_raw_top3)
            for _, row in work_df.iterrows()
        ],
        dtype=float,
    )
    
    # 최종 점수 계산 가중치
    final_score = (0.80 * t_final_sim) + (0.20 * top3_bonus_arr)

    result = work_df[
        [
            "id",
            "대분류",
            "중분류",
            "매핑 O*NET 직업명",
            "Top3",
            "참고 유사직업(1차)",
            "전공필수",
            "직무정보",
            *score_cols,
        ]
    ].copy()
    result["코사인유사도"] = cos_sim
    result["유클리드거리"] = dist
    result["거리기반유사도"] = dist_sim
    result["T점수유사도"] = t_final_sim
    result["Top3보정점수"] = top3_bonus_arr
    result["최종유사도"] = final_score
    result = result.sort_values(
        by=["최종유사도", "T점수유사도", "코사인유사도"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return result.head(top_n), user_scores


def recommended_jobs_payload(user_scores: dict[str, dict[str, int]], top_n: int = 10) -> list[dict]:
    result_df, _ = recommend_jobs_for_user_profile(user_scores, top_n=top_n)
    return [serialize_job(row, rank=index + 1) for index, (_, row) in enumerate(result_df.iterrows())]


def search_jobs(query: str, limit: int = 12) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    query = query.strip()
    if not query:
        rows = query_job_rows(f"{JOB_SELECT_SQL} ORDER BY id LIMIT %s", (limit,))
    else:
        like_query = f"%{query}%"
        rows = query_job_rows(
            f"""
            {JOB_SELECT_SQL}
            WHERE JK_L_category LIKE %s
               OR JK_M_category LIKE %s
               OR similar_job_name LIKE %s
               OR job_information LIKE %s
            ORDER BY id
            LIMIT %s
            """,
            (like_query, like_query, like_query, like_query, limit),
        )
    return [serialize_db_job(row) for row in rows]


def get_job_by_id(job_id: int) -> dict | None:
    rows = query_job_rows(f"{JOB_SELECT_SQL} WHERE id = %s LIMIT 1", (job_id,))
    if not rows:
        return None
    return serialize_db_job(rows[0])


def get_job_by_title(title: str) -> dict | None:
    exact_rows = query_job_rows(f"{JOB_SELECT_SQL} WHERE JK_M_category = %s ORDER BY id LIMIT 1", (title,))
    if exact_rows:
        return serialize_db_job(exact_rows[0])

    partial_rows = query_job_rows(f"{JOB_SELECT_SQL} WHERE JK_M_category LIKE %s ORDER BY id LIMIT 1", (f"%{title}%",))
    if partial_rows:
        return serialize_db_job(partial_rows[0])
    return None


def save_uploaded_pdf(uploaded_file) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        return tmp.name
