# Отчет об аудите файловой системы Jarvis

Дата: 2026-01-20
Проверка: Интеграция субтитров и общая архитектура

## 🔴 Критические проблемы

### 1. **Субтитры не интегрированы в production pipeline**

**Проблема:**
- Субтитры реализованы только в `modules/video_editor.py` (метод `_create_subtitle_filter()`)
- `VideoEditorModule` НЕ используется в `workers/worker.py` (production pipeline)
- `reels_renderer.py` (используется в worker) НЕ поддерживает субтитры
- Worker рендерит reels БЕЗ субтитров, хотя слова доступны в manifest

**Где используется:**
- ✅ `modules/video_editor.py` - есть субтитры (но модуль не используется в worker)
- ❌ `modules/reels_renderer.py` - НЕТ субтитров (используется в worker)
- ❌ `workers/worker.py` - НЕТ субтитров
- ❌ `local_cut.py` - НЕТ субтитров

**Решение:**
1. Добавить поддержку субтитров в `reels_renderer.py`
2. Передать слова из worker в `render_reels()`
3. Использовать логику из `video_editor.py` или вынести в отдельный модуль

---

### 2. **Дублирование функциональности транскрипции**

**Проблема:**
- `modules/video_editor.py` имеет метод `_transcribe()` (строки 195-235)
- `modules/transcribe.py` имеет функцию `transcribe_to_segments()`
- Оба используют faster-whisper, но с разными интерфейсами

**Где используется:**
- `video_editor.py._transcribe()` - только в VideoEditorModule (не используется в production)
- `transcribe.py.transcribe_to_segments()` - используется в worker и local_cut.py

**Решение:**
- Удалить `_transcribe()` из `video_editor.py` и использовать `transcribe_to_segments()`
- Или оставить только один интерфейс

---

### 3. **VideoEditorModule не используется в production**

**Проблема:**
- `VideoEditorModule` зарегистрирован в `core/jarvis.py` (JARVIS core)
- НО worker использует отдельные модули напрямую, а не через JARVIS core
- VideoEditorModule содержит полезный код (субтитры, face tracking), но он недоступен

**Где используется:**
- `core/jarvis.py` - регистрирует VideoEditorModule
- `workers/worker.py` - НЕ использует JARVIS core, работает напрямую с модулями

**Решение:**
- Либо интегрировать JARVIS core в worker
- Либо вынести функциональность из VideoEditorModule в отдельные модули
- Либо удалить VideoEditorModule, если он не нужен

---

## ⚠️ Проблемы интеграции

### 4. **Настройки субтитров не используются**

**Проблема:**
- В `config/settings.py` есть настройки субтитров (строки 60-66):
  - `subtitle_words_per_chunk`
  - `subtitle_font_size`
  - `subtitle_font`
  - `subtitle_color`
  - `subtitle_stroke_color`
  - `subtitle_stroke_width`
- Эти настройки используются ТОЛЬКО в `video_editor.py` (который не используется в worker)

**Решение:**
- Использовать эти настройки в `reels_renderer.py` при добавлении субтитров

---

### 5. **Отсутствует параметр для включения субтитров в API**

**Проблема:**
- В `api/server.py` в `JobCreateRequest` нет параметра `enable_subtitles` или `subtitles`
- Невозможно включить субтитры через API

**Решение:**
- Добавить параметр `subtitles: Optional[dict]` в `JobCreateRequest`
- Передать этот параметр в worker и далее в `render_reels()`

---

### 6. **local_cut.py не поддерживает субтитры**

**Проблема:**
- Локальный скрипт `local_cut.py` не добавляет субтитры в выходные клипы
- Хотя слова доступны после транскрипции

**Решение:**
- Добавить опцию `--subtitles` в `local_cut.py`
- Использовать логику субтитров при рендеринге

---

## 📋 Дублирование кода

### 7. **Дублирование работы с FFmpeg**

**Проблема:**
- `video_editor.py` строит сложные filter_complex с субтитрами
- `reels_renderer.py` строит простые фильтры без субтитров
- `video_cutter.py` строит команды для нарезки

**Решение:**
- Вынести логику создания subtitle filter в отдельную функцию
- Использовать её и в `video_editor.py`, и в `reels_renderer.py`

---

## 🔧 Рекомендации по исправлению

### Приоритет 1 (Критично):
1. ✅ Добавить субтитры в `reels_renderer.py`
2. ✅ Передать слова из worker в `render_reels()`
3. ✅ Добавить параметр `subtitles` в API

### Приоритет 2 (Важно):
4. ✅ Вынести логику субтитров в отдельный модуль `modules/subtitle_renderer.py`
5. ✅ Удалить дублирование транскрипции (использовать только `transcribe.py`)

### Приоритет 3 (Улучшения):
6. ✅ Добавить субтитры в `local_cut.py`
7. ✅ Решить судьбу `VideoEditorModule` (использовать или удалить)

---

## 📝 Файлы, требующие изменений

1. **modules/reels_renderer.py** - добавить поддержку субтитров
2. **workers/worker.py** - передать слова в `render_reels()`
3. **api/server.py** - добавить параметр `subtitles` в `JobCreateRequest`
4. **modules/video_editor.py** - удалить `_transcribe()` или использовать `transcribe.py`
5. **local_cut.py** - добавить опцию субтитров (опционально)

---

## ✅ Что работает хорошо

- ✅ Модульная архитектура (отдельные модули для разных задач)
- ✅ Worker правильно использует транскрипцию из `transcribe.py`
- ✅ Настройки субтитров уже есть в `config/settings.py`
- ✅ Логика субтитров уже реализована в `video_editor.py` (можно переиспользовать)

---

## 🎯 Выводы

**Главная проблема:** Субтитры сделаны DimaTorzok в `video_editor.py`, но этот модуль не используется в production pipeline (worker). Нужно интегрировать субтитры в `reels_renderer.py`, который реально используется.

**Что нужно сделать:**
1. Вынести логику субтитров из `video_editor.py` в отдельную функцию/модуль
2. Добавить поддержку субтитров в `reels_renderer.py`
3. Передать слова из worker в `render_reels()`
4. Добавить параметр в API для включения субтитров

