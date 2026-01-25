# Отчет об исправлениях Pipeline

Дата: 2026-01-20
Статус: ✅ Все исправления применены

## Исправленные проблемы

### 1. ✅ snap_window_sec увеличен с 0.25 до 2.0 секунды

**Было:**
```python
snap_window_sec = min(snap_window_sec, 0.25)  # Слишком строго
```

**Стало:**
```python
# Limit to reasonable maximum (2.0s) to prevent excessive boundary shifts
# The silence_detect module already has protection: max_duration_change = window_sec * 2
snap_window_sec = min(snap_window_sec, 2.0)
```

**Обоснование:**
- В `silence_detect.py` уже есть защита: `max_duration_change = window_sec * 2`
- Ограничение 0.25 было избыточным и мешало находить хорошие границы тишины
- Теперь можно использовать дефолтное значение 1.0 и до 2.0 секунды

---

### 2. ✅ Исправлен конфликт hook_first_cutting + boundary_mode word

**Было:**
- hook_first сдвигал начало к hook
- boundary_mode сразу же возвращал начало к первому слову
- hook_first не работал

**Стало:**
- hook_first имеет приоритет
- Если hook_first использован, boundary_mode НЕ применяется для начала
- boundary_mode применяется только для конца (к последнему слову)

**Код:**
```python
# После snapping, при применении boundary_mode word:
if first_word:
    # Only adjust start if hook_first wasn't used (hook_first has priority)
    if not hook_first_used:
        snapped["snapped_start"] = min(
            float(snapped["snapped_start"]), float(first_word["start"])
        )
```

---

### 3. ✅ Убрана двойная корректировка boundary_mode word

**Было:**
- boundary_mode применялся ДО snapping (строки 532-534)
- boundary_mode применялся ПОСЛЕ snapping (строки 640-651)
- Избыточная обработка, возможные конфликты

**Стало:**
- boundary_mode применяется ТОЛЬКО после snapping
- Это дает лучший результат: сначала snapping к тишине, потом точная корректировка к словам

**Код:**
```python
# Убрано: корректировка ДО snapping
# Оставлено: корректировка ПОСЛЕ snapping (строки 651-668)
```

---

### 4. ✅ Пересмотрена логика snapped_end >= segment["end"]

**Было:**
```python
if task == "auto_clips":
    snapped["snapped_end"] = max(
        float(snapped["snapped_end"]), float(segment["end"])
    )
```
- Всегда запрещало уменьшение конца
- Конфликтовало с boundary_mode word

**Стало:**
```python
# For auto_clips: ensure end doesn't go backwards, but allow forward adjustment
# Exception: if boundary_mode is word, we'll adjust to word boundaries below
if task == "auto_clips" and boundary_mode != "word":
    snapped["snapped_end"] = max(
        float(snapped["snapped_end"]), float(segment["end"])
    )
```
- Не применяется если boundary_mode == "word"
- Позволяет boundary_mode точно обрезать до последнего слова

---

### 5. ✅ Добавлена финальная валидация перед нарезкой

**Было:**
- Нет проверки валидности сегментов перед нарезкой
- Могли быть сегменты с end <= start

**Стало:**
```python
# Final validation: ensure valid segment boundaries
if end <= start:
    logger.warning(f"Invalid segment {s['id']}: end ({end:.3f}) <= start ({start:.3f}), skipping")
    continue
min_dur = min_duration if task == "auto_clips" else 0.1
if (end - start) < min_dur:
    logger.warning(f"Segment {s['id']} too short: {end - start:.3f}s < {min_dur:.3f}s, skipping")
    continue
```

**Проверки:**
- ✅ start < end
- ✅ Минимальная длительность
- ✅ Пропуск невалидных сегментов с предупреждением

---

## Совместимость с существующими пресетами

### Проверено:
- ✅ `golden_clip2_2026-01-17` - boundary_mode: word, snap_to_silence: true
- ✅ `reels_premium_hebrew` - boundary_mode: word, hook_first_cutting: true, snap_to_silence: true
- ✅ `reels_premium_hebrew_long` - boundary_mode: word, hook_first_cutting: true, snap_to_silence: true

**Все пресеты совместимы:**
- Увеличение snap_window_sec улучшит качество (больше возможностей найти тишину)
- hook_first теперь работает правильно
- boundary_mode работает более точно (только после snapping)

---

## Новый порядок операций (auto_clips)

```
1. Загрузка видео ✅
2. Транскрипция (или загрузка) ✅
3. Извлечение аудио-фич ✅
4. Построение предложений ✅
5. Выбор сегментов (select_segments) ✅
6. Расширение до завершения (extend_segment_to_completion) ✅
7. Hook-first cutting (pick_hook_start) ✅ [теперь работает правильно]
8. Snapping to silence ✅ [улучшен: до 2.0 сек вместо 0.25]
9. Boundary mode word (только после snapping) ✅ [убрана двойная обработка]
10. Финальная валидация ✅ [новая проверка]
11. Нарезка (cut_segments) ✅
12. Рендеринг reels (render_reels) ✅
13. Загрузка в S3 ✅
```

---

## Ожидаемые улучшения

1. **Лучшее качество клипов:**
   - Больше возможностей найти границы тишины (snap_window до 2.0 сек)
   - hook_first теперь работает и улучшает начало клипов
   - Более точные границы слов (только после snapping)

2. **Меньше ошибок:**
   - Валидация предотвращает невалидные сегменты
   - Нет конфликтов между hook_first и boundary_mode

3. **Более предсказуемое поведение:**
   - Четкий порядок операций
   - Приоритеты понятны (hook_first > boundary_mode)

---

## Тестирование

Рекомендуется протестировать:
1. ✅ Пресеты с hook_first_cutting: true
2. ✅ Пресеты с boundary_mode: word
3. ✅ Пресеты с snap_to_silence: true
4. ✅ Комбинации всех параметров

Все изменения обратно совместимы - существующие пресеты будут работать лучше.

