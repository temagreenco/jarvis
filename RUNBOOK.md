# RUNBOOK

## Что делать если упало
1) Проверить статус контейнеров:
```
docker compose ps
```
2) Посмотреть логи проблемного сервиса:
```
docker compose logs --tail=200 api
```
3) Перезапустить только упавший сервис:
```
docker compose restart api
```
4) Если ошибка повторяется, собрать диагностические данные:
```
docker compose logs --tail=500 api > api.log
```

## Как смотреть логи
- API:
```
docker compose logs --tail=200 api
```
- Worker:
```
docker compose logs --tail=200 worker_cpu
```
- Postgres:
```
docker compose logs --tail=200 postgres
```
- Redis:
```
docker compose logs --tail=200 redis
```

## Как рестартить сервис
- Один сервис:
```
docker compose restart api
```
- Все сервисы:
```
docker compose restart
```

## Бэкапы
- Запуск разового бэкапа (Postgres dump + архивы MinIO/Redis):
```
.\scripts\backup_all.ps1 -BackupRoot "F:\dev\backups"
```

## Восстановление
- Восстановить всё из директории бэкапа:
```
.\scripts\restore_all.ps1 -BackupDir "F:\dev\backups\jarvis\YYYYMMDD-HHMMSS"
```
