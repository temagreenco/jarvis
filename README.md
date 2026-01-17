# Jarvis

## Как запустить локально
1) Поднять инфраструктуру и сервисы:
```
docker compose up -d minio postgres redis api worker_cpu
```
2) Проверить статус:
```
docker compose ps
```
3) Проверить API:
```
curl.exe "http://localhost:8000/health"
```

## Как запустить на сервере
1) На сервере установите Docker и Docker Compose.
2) Скопируйте репозиторий и настройте переменные окружения (см. SECURITY.md).
3) Запуск:
```
docker compose up -d
```
4) Проверка:
```
docker compose ps
```

## Основные команды
- Старт: `docker compose up -d`
- Остановка: `docker compose down`
- Статус: `docker compose ps`
- Логи: `docker compose logs --tail=200 api`
- Рестарт сервиса: `docker compose restart api`
- Тест auto_clips:
```
.\scripts\submit_auto_clips_job.ps1 -InputPath "C:\path\to\video.mp4"
```

## Presets
Run static reels center framing preset:
```
.\scripts\submit_auto_clips_job.ps1 -InputPath "C:\path\to\video.mp4" -Preset reels_static_center
```
