# Cloud Run Deployment

FastAPI 앱은 Cloud Run에서 실행하고, 직무 카탈로그는 Supabase `public."JK_job"` 테이블에서 조회합니다. GitHub에는 실제 API 키를 올리지 말고, 로컬/배포 환경변수는 `.env.example`을 기준으로 별도 설정합니다.

## Required Environment Variables

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`, 기본값 `gpt-5-mini`

`OPENAI_API_KEY`는 비밀값입니다. Supabase `service_role` key나 `sb_secret_` key는 이 앱에 필요하지 않으며, 절대 GitHub나 프론트엔드에 노출하지 않습니다.

## Deploy

아래 명령은 기존 Cloud SQL 연결과 MySQL 환경변수를 제거하고, Supabase 환경변수로 교체합니다.

```powershell
$GCP_PROJECT_ID = "<GCP_PROJECT_ID>"
$GCP_PROJECT_NUMBER = "<GCP_PROJECT_NUMBER>"
$SERVICE_NAME = "nobijobara-api"
$REGION = "asia-northeast3"
$SUPABASE_URL = "https://<SUPABASE_PROJECT_REF>.supabase.co"
$SUPABASE_PUBLISHABLE_KEY = "<SUPABASE_PUBLISHABLE_KEY>"
$OPENAI_API_KEY = "<OPENAI_API_KEY>"

gcloud config set project $GCP_PROJECT_ID

gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID `
  --member="serviceAccount:$GCP_PROJECT_NUMBER-compute@developer.gserviceaccount.com" `
  --role="roles/run.builder"

gcloud run deploy $SERVICE_NAME `
  --region $REGION `
  --source . `
  --allow-unauthenticated `
  --clear-cloudsql-instances `
  --remove-env-vars INSTANCE_CONNECTION_NAME,MYSQL_HOST,MYSQL_PORT,MYSQL_USER,MYSQL_PASSWORD,MYSQL_DATABASE,MYSQL_CONNECT_TIMEOUT `
  --update-env-vars "SUPABASE_URL=$SUPABASE_URL,SUPABASE_PUBLISHABLE_KEY=$SUPABASE_PUBLISHABLE_KEY,OPENAI_API_KEY=$OPENAI_API_KEY,OPENAI_MODEL=gpt-5-mini"
```

## Verify Deployment

```powershell
gcloud run services describe $SERVICE_NAME `
  --region $REGION `
  --format="yaml(spec.template.metadata.annotations,spec.template.spec.containers[0].env,status.url)"
```

응답에서 Cloud SQL annotation이 비어 있고, `MYSQL_*` 환경변수가 없어야 합니다.

```powershell
$CLOUD_RUN_URL = "<CLOUD_RUN_URL>"

curl.exe -s "$CLOUD_RUN_URL/health"
curl.exe -s "$CLOUD_RUN_URL/catalog/search?query=DBA"
```

## Supabase Data Check

Supabase SQL Editor 또는 MCP에서 데이터가 들어 있는지 확인합니다.

```sql
select count(*) from public."JK_job";
select id, "JK_L_category", "JK_M_category", top3
from public."JK_job"
order by id
limit 5;
```
