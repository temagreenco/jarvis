# SECURITY

## Где секреты
- Переменные окружения (рекомендуется файл `.env` рядом с `docker-compose.yml`).
- Ключи AI-провайдеров: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `CLAUDE_API_KEY`.
- Доступ к MinIO: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`.
- Прочие настройки: `DEFAULT_AI_PROVIDER`, `PRESIGN_EXPIRES_SECONDS`, `JARVIS_WHISPER_MODEL`.

## Кто имеет доступ
- Доступ к секретам имеют только администраторы среды запуска (DevOps/infra).
- Доступ к MinIO/DB ограничивается сетью контейнеров (`jarvis-net`).
- Публичные эндпоинты (API) должны быть закрыты авторизацией на уровне инфраструктуры.

## Правила ключей/паролей
- Не хранить секреты в репозитории.
- Использовать `.env` или секрет-хранилища платформы (Vault, AWS/GCP secrets, etc.).
- Ротация ключей при утечке или смене доступа.
- Минимальные права для ключей (least privilege).

