from urllib.parse import quote_plus
import pandas as pd
import sqlalchemy as sa
from difflib import SequenceMatcher

# DB 연결 정보
DB_HOST = "34.50.27.132"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "slavejob1234@"
DB_NAME = "slave_job"

def get_engine():
    encoded_pw = quote_plus(DB_PASSWORD)

    db_url = (
        f"mysql+pymysql://{DB_USER}:{encoded_pw}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    return sa.create_engine(db_url)

def load_job_data():
    engine = get_engine()
    query = """
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
        job_definition
    FROM JK_job
    """
    return pd.read_sql(query, engine)

def similarity(a, b):
    if pd.isna(a) or pd.isna(b):
        return 0.0
    return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def search_similar_jobs(query, df, top_n=5):
    query = str(query).strip().lower()
    results = []

    for _, row in df.iterrows():
        jk_job = str(row.get("JK_M_category", "")).strip()
        similar_job = str(row.get("similar_job_name", "")).strip()
        job_def = str(row.get("job_definition", "")).strip()

        # 기본 유사도 점수
        score_jk = similarity(query, jk_job) * 0.5
        score_similar = similarity(query, similar_job) * 0.3
        score_def = similarity(query, job_def) * 0.2

        # 부분 포함 보너스
        bonus = 0.0
        if query in jk_job.lower():
            bonus += 0.4
        if query in similar_job.lower():
            bonus += 0.25
        if query in job_def.lower():
            bonus += 0.15

        total_score = score_jk + score_similar + score_def + bonus

        results.append({
            "id": row["id"],
            "JK대분류": row["JK_L_category"],
            "JK중분류": jk_job,
            "유사 O*NET 직업명": similar_job,
            "Top3": row.get("top3"),
            "검색점수": round(total_score, 4),
            "직무정의": job_def
        })

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values(by="검색점수", ascending=False)

    # 같은 직무명 중복 제거
    result_df = result_df.drop_duplicates(subset=["JK중분류"])

    return result_df.head(top_n).reset_index(drop=True)

def make_search_response(result_df):
    if result_df.empty:
        return "검색 결과와 유사한 직무를 찾지 못했습니다."

    text = "입력하신 직무와 관련도가 높은 직무는 아래와 같습니다.\n\n"
    for i, (_, row) in enumerate(result_df.iterrows(), start=1):
        text += f"{i}. {row['JK중분류']} - {row['유사 O*NET 직업명']}\n"

    text += "\n관심 있는 직무를 선택해주시면 해당 기준으로 준비 로드맵을 안내해드릴게요."
    return text

if __name__ == "__main__":
    df = load_job_data()

    query = input("검색할 직무를 입력하세요: ")
    result = search_similar_jobs(query, df, top_n=5)

    print("\n[유사 직무 검색 결과]")
    print(result[["id", "JK중분류", "유사 O*NET 직업명", "검색점수"]])

    print("\n[챗봇 응답 예시]")
    print(make_search_response(result))