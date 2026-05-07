# Cloud Run 배포 메모

이 프로젝트는 Cloud Run에서 FastAPI 전체 앱을 실행하고, Cloud SQL `slavejob` 인스턴스에는 Cloud SQL Unix socket으로 연결합니다.

## 필요한 값

- Cloud SQL 인스턴스 ID: `slavejob`
- Cloud SQL 연결 이름 예시: `project-ea8c13da-7dcf-443e-a47:asia-northeast3:slavejob`
- 필수 환경변수:
  - `INSTANCE_CONNECTION_NAME`
  - `MYSQL_USER`
  - `MYSQL_PASSWORD`
  - `MYSQL_DATABASE`
  - `MYSQL_CONNECT_TIMEOUT`, 기본값 `5`
- 선택 환경변수:
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`

`OPENAI_API_KEY`가 없어도 앱은 동작합니다. 이 경우 로드맵은 OpenAI 호출 대신 내부 fallback 로드맵으로 생성됩니다.

## Cloud Run 환경에서 DB 연결 방식

Cloud Run에서는 `MYSQL_HOST`를 사용하지 않습니다.

`INSTANCE_CONNECTION_NAME`이 있으면 코드가 아래 socket으로 MySQL에 연결합니다.

```txt
/cloudsql/{INSTANCE_CONNECTION_NAME}
```

로컬 개발에서는 기존처럼 `.env`의 `MYSQL_HOST`, `MYSQL_PORT`를 사용합니다.

## 배포 명령 예시

```powershell
cd "C:\Users\dkstj\OneDrive\DESKTOP\잡다한거\src_fastapi"

gcloud config set project project-ea8c13da-7dcf-443e-a47

gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com

gcloud projects add-iam-policy-binding project-ea8c13da-7dcf-443e-a47 `
  --member="serviceAccount:962802112105-compute@developer.gserviceaccount.com" `
  --role="roles/run.builder"

gcloud projects add-iam-policy-binding project-ea8c13da-7dcf-443e-a47 `
  --member="serviceAccount:962802112105-compute@developer.gserviceaccount.com" `
  --role="roles/cloudsql.client"

gcloud run deploy nobijobara-api `
  --region asia-northeast3 `
  --source . `
  --allow-unauthenticated `
  --add-cloudsql-instances project-ea8c13da-7dcf-443e-a47:asia-northeast3:slavejob `
  --set-env-vars "INSTANCE_CONNECTION_NAME=project-ea8c13da-7dcf-443e-a47:asia-northeast3:slavejob,MYSQL_USER=DB_USER,MYSQL_PASSWORD=DB_PASSWORD,MYSQL_DATABASE=DB_NAME,MYSQL_CONNECT_TIMEOUT=5"
```

`DB_USER`, `DB_PASSWORD`, `DB_NAME`은 실제 Cloud SQL MySQL 계정 값으로 바꿔야 합니다.
