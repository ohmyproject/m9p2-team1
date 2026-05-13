import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# .env 로드
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_KEY")
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print(f"DEBUG: SUPABASE_URL={'Set' if SUPABASE_URL else 'Not Set'}")
print(f"DEBUG: SUPABASE_KEY={'Set' if SUPABASE_KEY else 'Not Set'}")
print(f"DEBUG: OPENAI_API_KEY={'Set' if OPENAI_API_KEY else 'Not Set'}")

if not SUPABASE_URL or not SUPABASE_KEY or not OPENAI_API_KEY:
    print("환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    return openai_client.embeddings.create(input=[text], model=model).data[0].embedding

def embed_jobs():
    print("데이터 조회 중...")
    # 모든 직무 데이터 가져오기 (id, JK_M_category, job_information)
    response = supabase.table("JK_job").select("id, JK_M_category, job_information").execute()
    jobs = response.data
    
    print(f"총 {len(jobs)}개의 직무 데이터를 처리합니다.")
    
    for i, job in enumerate(jobs):
        job_id = job["id"]
        title = job["JK_M_category"] or ""
        info = job["job_information"] or ""
        
        # 임베딩할 텍스트 결합
        combined_text = f"직무명: {title}\n상세정보: {info}"
        
        if not combined_text.strip():
            continue
            
        try:
            print(f"[{i+1}/{len(jobs)}] '{title}' 임베딩 생성 중...")
            embedding = get_embedding(combined_text)
            
            # DB 업데이트
            supabase.table("JK_job").update({"embedding": embedding}).eq("id", job_id).execute()
        except Exception as e:
            print(f"오류 발생 (ID {job_id}): {e}")
            continue

    print("모든 임베딩 작업이 완료되었습니다.")

if __name__ == "__main__":
    embed_jobs()
