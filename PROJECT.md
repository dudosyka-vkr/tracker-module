# Документация проекта EyeTracker

## Структура проекта

```
eyetracker/
├── pyproject.toml                             # Конфигурация Poetry, зависимости
├── Makefile                                   # Команды: install, run, test, build, clean
├── eyetracker.spec                            # PyInstaller спецификация сборки
├── entitlements.plist                         # macOS entitlements (доступ к камере)
├── eyetracker/
│   ├── __init__.py                            # Версия пакета
│   ├── main.py                                # CLI точка входа (argparse)
│   ├── app.py                                 # App — QMainWindow + QStackedWidget, навигация
│   ├── ui/                                    # UI слой
│   │   ├── theme.py                           # Константы стиля macOS (цвета, шрифты, размеры)
│   │   ├── pages/                             # Экраны/страницы
│   │   │   ├── home.py                        # HomeScreen — sidebar + контент + навигация
│   │   │   ├── calibration.py                 # CalibrationScreen + PrecisionCalculator
│   │   │   ├── create_test_page.py            # CreateTestChoicePage — выбор способа создания
│   │   │   ├── test_form_page.py              # TestFormPage — форма create/view/edit
│   │   │   ├── test_library_page.py           # TestLibraryPage — библиотека тестов
│   │   │   ├── test_run_screen.py             # TestRunScreen — последовательный показ изображений
│   │   │   ├── records_list_page.py           # RecordsListPage — таблица результатов теста
│   │   │   └── record_detail_page.py          # RecordDetailPage — детали записи + экспорт
│   │   └── widgets/                           # Переиспользуемые виджеты
│   │       └── image_grid.py                  # ImageGridWidget + превью + drag-to-reorder
│   ├── data/                                  # Слой данных
│   │   ├── settings.py                        # Settings — ~/.eyetracker/settings.json
│   │   ├── draft_cache.py                     # DraftCache — автосохранение черновиков форм
│   │   ├── login/                             # Модуль авторизации
│   │   │   ├── service.py                     # LoginService ABC
│   │   │   └── local_service.py               # LocalLoginService — локальная заглушка
│   │   ├── record/                            # Модуль записей результатов
│   │   │   ├── service.py                     # RecordService ABC + Record, RecordSummary, RecordQuery
│   │   │   └── local_service.py               # LocalRecordService — ~/.eyetracker/records/
│   │   └── test/                              # Модуль тестов
│   │       ├── dao.py                         # TestData + TestDao ABC
│   │       └── local_dao.py                   # LocalTestDao — ~/.eyetracker/tests/<id>/
│   ├── core/                                  # Ядро (pipeline, утилиты)
│   │   ├── pipeline.py                        # Трекер, регрессия, детекция моргания, сохранение/загрузка калибровки
│   │   ├── util.py                            # Eye, DataWindow, KalmanFilter
│   │   ├── monitor.py                         # Выбор монитора для трекинга
│   │   ├── metrics.py                         # GazeMetricsAggregator — агрегация метрик взгляда
│   │   ├── fixation.py                        # FixationDetector — детекция фиксаций в реальном времени
│   │   ├── face_emotion.py                    # FaceEmotionRecognition — распознавание эмоций (заглушка)
│   │   ├── heatmap.py                         # Генерация тепловой карты взгляда (Gaussian + JET colormap)
│   │   ├── fixation_map.py                    # Рендер фиксационной карты (круг + номер + эмоция поверх изображения)
│   │   ├── report_export.py                   # Экспорт записи в ZIP-архив (per-image папки)
│   │   └── time_fmt.py                        # Форматирование ISO 8601 → DD.MM.YYYY HH:MM
│   └── models/                                # Автоматически скачиваемая модель
└── tests/
    ├── test_util.py                           # 18 тестов
    ├── test_regression.py                     # 5 тестов
    ├── test_blink.py                          # 3 теста
    ├── test_precision.py                      # 4 теста
    ├── test_settings.py                       # 9 тестов
    ├── test_monitor.py                        # 4 теста
    ├── test_test_dao.py                       # 15 тестов
    ├── test_create_test_form.py               # 6 тестов
    ├── test_draft_cache.py                    # 8 тестов
    ├── test_login_service.py                  # 3 теста
    ├── test_metrics.py                        # 5 тестов
    ├── test_record_service.py                 # 8 тестов
    ├── test_heatmap.py                        # 10 тестов
    ├── test_report_export.py                  # 8 тестов
    ├── test_time_fmt.py                       # 4 теста
    └── test_fixation.py                       # 5 тестов
```

## Зависимости

| Пакет | Назначение |
|-------|-----------|
| `numpy` | Матричные операции, линейная алгебра |
| `opencv-python` | Захват видео, обработка изображений |
| `mediapipe` | Детекция лица и ландмарков (FaceLandmarker) |
| `PyQt6` | GUI калибровки и отслеживания |
| `pyinstaller` | Сборка в нативное приложение (dev) |

---

## Пайплайн предсказания взгляда

Полный цикл предсказания реализован в `pipeline.py:EyeTracker._loop()`:

```
Кадр веб-камеры (BGR)
    ↓
MediaPipeTracker.get_eye_patches(frame)
    ↓
(left_eye: Eye, right_eye: Eye, landmarks: list)
    ↓
BlinkDetector.detect_blink(left, right)
    ↓
RidgeWeightedReg.predict(left, right)
    ↓
Сглаживание через DataWindow(4)
    ↓
bound() — ограничение координат экраном
    ↓
callback(gaze_data, elapsed)
```

Цикл работает в фоновом потоке с периодом `data_timestep` (50 мс по умолчанию):

```python
# pipeline.py:183-231
def _loop(self):
    while self._running:
        if self._paused:
            time.sleep(0.01)
            continue
        ret, frame = self._cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        self._latest_frame = frame
        result = self._tracker.get_eye_patches(frame)
        if result is None:
            self._latest_eye_features = None
            time.sleep(self.params.data_timestep / 1000.0)
            continue
        left, right, landmarks = result
        self._latest_landmarks = landmarks
        self._blink_detector.detect_blink(left, right, blink_detection_on=True)
        self._latest_eye_features = (left, right)
        gaze = self._get_prediction(left, right)
        elapsed = time.time() - self._clock_start
        if gaze:
            self._smoothing.push(gaze)
            sx = sum(self._smoothing.get(i)["x"] for i in range(self._smoothing.length)) / self._smoothing.length
            sy = sum(self._smoothing.get(i)["y"] for i in range(self._smoothing.length)) / self._smoothing.length
            gaze = bound({"x": sx, "y": sy}, self._screen_width, self._screen_height)
        self._latest_gaze = gaze
        if self._callback:
            self._callback(gaze, elapsed)
        time.sleep(self.params.data_timestep / 1000.0)
```

---

## Модули

### 1. Трекер лица — `pipeline.py:MediaPipeTracker`

Использует `mediapipe.tasks.vision.FaceLandmarker` (Tasks API) для обнаружения 478 лицевых ландмарков. Модель `face_landmarker.task` скачивается автоматически при первом запуске.

**Режим работы**: `RunningMode.VIDEO` — оптимизирован для последовательных кадров с отслеживанием между кадрами.

**Извлечение патча глаза** — из найденных ландмарков берутся индексы контура глаза и вырезается прямоугольная область из кадра:

```python
# pipeline.py:124-140
def _extract_eye_patch(self, frame, landmarks, indices, kalman):
    pts = [landmarks[i] for i in indices]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_min = max(0, min(xs))
    y_min = max(0, min(ys))
    x_max = min(w, max(xs))
    y_max = min(h, max(ys))
    if self.smooth_eye_bb:
        box = [x_min, y_min, x_max, y_max]
        smoothed = kalman.update(box)
        x_min = max(0, round(smoothed[0]))
        ...
    bgr_patch = frame[y_min:y_max, x_min:x_max]
    rgba_patch = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2RGBA)
    return Eye(rgba_patch.ravel(), x_min, y_min, eye_w, eye_h)
```

Индексы контуров глаз:
```python
# pipeline.py:15-18
LEFT_EYE_INDICES = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE_INDICES = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
```

#### Сглаживание Калмана

Координаты ограничивающих прямоугольников глаз (bounding box) могут дрожать от кадра к кадру из-за шума детекции ландмарков. Для устранения этого применяется фильтр Калмана (включён по умолчанию).

**Вектор состояния** — 6 компонент: `[x_min, y_min, x_max, y_max, vx, vy]`, где первые 4 — координаты углов bounding box, а `vx`, `vy` — скорости изменения координат.

**Матрица перехода** `F` (6x6) — модель постоянной скорости:

```python
# pipeline.py:69-76
F = [
    [1, 0, 0, 0, 1, 0],   # x_min += vx
    [0, 1, 0, 0, 0, 1],   # y_min += vy
    [0, 0, 1, 0, 1, 0],   # x_max += vx
    [0, 0, 0, 1, 0, 1],   # y_max += vy
    [0, 0, 0, 0, 1, 0],   # vx = const
    [0, 0, 0, 0, 0, 1],   # vy = const
]
```

**Матрица наблюдения** `H` (4x6) — наблюдаем только координаты, не скорости:

```python
# pipeline.py:86-91
H = [
    [1, 0, 0, 0, 0, 0],
    [0, 1, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 0],
    [0, 0, 0, 1, 0, 0],
]
```

**Параметры шума:**
- `Q` — шум процесса, масштабированный на `delta_t = 1/10` (период между кадрами)
- `R = eye(4) * 6.5` — шум наблюдения (погрешность детекции ~6.5 пикселей)
- `P_initial = eye(6) * 0.0001` — начальная неопределённость (низкая, т.к. начальная позиция задана)

**Цикл обновления** в `KalmanFilter.update()`:

```python
# util.py:183-198
def update(self, z: list[float]) -> list[float]:
    z_col = np.array(z, dtype=np.float64).reshape(-1, 1)
    # Prediction: X_p = F @ X,  P_p = F @ P @ F' + Q
    X_p = self.F @ self.X
    P_p = self.F @ self.P @ self.F.T + self.Q
    # Update: K = P_p @ H' @ (H @ P_p @ H' + R)^-1
    y = z_col - self.H @ X_p
    S = self.H @ P_p @ self.H.T + self.R
    K = P_p @ self.H.T @ np.linalg.inv(S)
    self.X = X_p + K @ y
    self.P = (np.eye(K.shape[0]) - K @ self.H) @ P_p
    return (self.H @ self.X).flatten().tolist()
```

1. **Predict** — экстраполируем позицию bounding box на основе предыдущей скорости
2. **Update** — корректируем предсказание по фактическим измерениям от MediaPipe
3. **Результат** — сглаженные координаты `[x_min, y_min, x_max, y_max]`, по которым вырезается патч глаза

Фильтр создаётся отдельно для каждого глаза (`left_kalman`, `right_kalman`), т.к. глаза двигаются независимо. Применяется в `_extract_eye_patch()` перед вырезкой патча:

```python
# pipeline.py:143-149
if self.smooth_eye_bb:
    box = [x_min, y_min, x_max, y_max]
    smoothed = kalman.update(box)
    x_min = max(0, round(smoothed[0]))
    y_min = max(0, round(smoothed[1]))
    x_max = min(w, round(smoothed[2]))
    y_max = min(h, round(smoothed[3]))
```

**Эффект**: устраняет микро-дрожание патчей глаз между кадрами, что улучшает стабильность 120D вектора признаков и, как следствие, стабильность предсказания взгляда.

### 2. Извлечение признаков глаз — `pipeline.py:_get_eye_feats()`

Каждый патч глаза проходит через пайплайн предобработки, после чего формируется 120-мерный вектор признаков:

```python
# pipeline.py:49-63
def _get_eye_feats(left: Eye, right: Eye) -> list[float]:
    resized_left = resize_eye(left, 10, 6)     # 10x6 = 60 пикселей
    resized_right = resize_eye(right, 10, 6)

    left_gray = grayscale(resized_left.patch, resized_left.width, resized_left.height)
    right_gray = grayscale(resized_right.patch, resized_right.width, resized_right.height)

    hist_left = equalize_histogram(left_gray, 5)   # Выравнивание гистограммы
    hist_right = equalize_histogram(right_gray, 5)

    return hist_left.tolist() + hist_right.tolist()  # 60 + 60 = 120D
```

Этапы:
1. **Масштабирование** до 10x6 через `cv2.resize` с билинейной интерполяцией
2. **Градации серого** по формуле: `0.299*R + 0.587*G + 0.114*B`
3. **Выравнивание гистограммы** с шагом 5 — нормализует освещённость
4. **Конкатенация** — 60 значений левого + 60 значений правого глаза

### 3. Гребневая регрессия — `pipeline.py`

Решает задачу регрессии: `eye_features (120D) → screen_coordinates (x, y)`.

Модуль содержит функцию `_ridge()`, функцию извлечения признаков `_get_eye_feats()` и класс `RidgeWeightedReg`, который применяет экспоненциальное затухание к старым данным — более свежие калибровочные точки имеют больший вес.

**Формула**: `(X'X + kI) * β = X'y`, где `k = 1e-5` — параметр регуляризации.

```python
# pipeline.py:21-45
def _ridge(y: np.ndarray, X: np.ndarray, k: float) -> np.ndarray:
    success = False
    while not success:
        try:
            xt = X.T
            ss = xt @ X
            nc = ss.shape[0]
            for i in range(nc):
                ss[i, i] += k          # Регуляризация
            bb = xt @ y
            if ss.shape[0] == ss.shape[1]:
                coefficients = np.linalg.solve(ss, bb)
            else:
                coefficients, _, _, _ = np.linalg.lstsq(ss, bb, rcond=None)
            success = True
        except np.linalg.LinAlgError:
            k *= 10                     # Увеличиваем k если матрица вырождена
    return coefficients.flatten()
```

**Взвешивание** — при предсказании каждая калибровочная точка получает вес `sqrt(1 / (n - i))`, где `i` — порядковый номер точки. Недавние точки имеют больший вес, что позволяет модели адаптироваться к смещению головы.

**Хранение данных** — два типа буферов:
- `DataWindow(700)` — данные кликов калибровки (до 700 точек)
- `DataWindow(10)` — trail-данные от движения мыши (последняя 1 секунда)

### 4. Детекция моргания — `pipeline.py:BlinkDetector`

Определяет моргание через корреляцию обработанных кадров глаза:

```python
# pipeline.py:22-30
def _extract_blink_data(self, right_eye: Eye) -> dict:
    gray = grayscale(right_eye.patch, right_eye.width, right_eye.height)
    equalized = equalize_histogram(gray, EQUALIZE_STEP)
    thresholded = threshold(equalized, THRESHOLD_VALUE)
    return {"data": thresholded, "width": right_eye.width, "height": right_eye.height}
```

Сравнивается корреляция между последовательными кадрами в окне из 8 кадров. Корреляция в диапазоне `(0.78, 0.85)` считается морганием. При моргании данные калибровки не записываются.

### 5. Утилиты — `util.py`

**`Eye`** — структура данных патча глаза:
```python
# util.py:12-31
class Eye:
    __slots__ = ("patch", "imagex", "imagey", "width", "height", "blink", "pupil")
    def __init__(self, patch, imagex, imagey, width, height):
        self.patch = patch      # RGBA uint8, flat array
        self.imagex = imagex    # Координата X в исходном кадре
        self.imagey = imagey
        self.width = width
        self.height = height
        self.blink = False
        self.pupil = None       # (координаты, радиус) или None
```

**`DataWindow`** — кольцевой буфер фиксированного размера:
```python
# util.py:34-66
class DataWindow:
    def __init__(self, window_size: int, data: list | None = None):
        self.window_size = window_size
        self.index = 0
        self.data: list = []
    def push(self, entry) -> "DataWindow":
        if len(self.data) < self.window_size:
            self.data.append(entry)
            return self
        self.data[self.index] = entry
        self.index = (self.index + 1) % self.window_size
        return self
```

**`KalmanFilter`** — фильтр Калмана для сглаживания ограничивающих прямоугольников глаз. Подробное описание математической модели, матриц и параметров — в разделе [сглаживание Калмана](#сглаживание-калмана) выше.

### 6. Измерение точности — `calibration.py:PrecisionCalculator`

Собирает предсказания взгляда за 5-секундный интервал и вычисляет среднее расстояние до целевой точки:

```python
# calibration.py:35-55
def calculate_precision(self, target_x: float, target_y: float) -> float:
    n = min(self.index, self.window_size)
    if n == 0:
        return 0.0
    total_distance = 0.0
    for i in range(n):
        dx = self.x_points[i] - target_x
        dy = self.y_points[i] - target_y
        total_distance += math.sqrt(dx * dx + dy * dy)
    avg_distance = total_distance / n
    precision = max(0.0, 100.0 - avg_distance * 100.0 / 500.0)
    return round(precision, 2)
```

### 7. Настройки — `settings.py`

JSON-хранилище настроек приложения в `~/.eyetracker/settings.json`. Настройки:
- `tracking_display_name` — имя монитора для трекинга (`None` = основной)
- `auth_token` — JWT-токен авторизации (`None` = не авторизован)
- `skip_calibration` — пропускать фазу кликов по точкам калибровки (`false` по умолчанию); загружает сохранённые данные из `~/.eyetracker/calibration.json`
- `show_gaze_marker` — показывать точку взгляда во время прохождения теста (`false` по умолчанию)
- `last_opened_test_id` — ID последнего открытого теста (для восстановления состояния)
- `image_display_duration_ms` — длительность показа каждого изображения в мс (`5000` по умолчанию)
- `tracking_timestep_ms` — период опроса трекера в мс (`50` по умолчанию)
- `fixation_enabled` — включить детекцию фиксаций во время теста (`true` по умолчанию)
- `fixation_radius_threshold_k` — порог радиуса фиксации в пикселях экрана (`80.0` по умолчанию)
- `fixation_window_size_samples` — размер скользящего окна (в отсчётах) для детекции фиксаций (`10` по умолчанию)

### 8. Выбор монитора — `monitor.py`

Утилиты для работы с мониторами:
- `get_available_screens()` — список доступных экранов через `QApplication.screens()`
- `resolve_screen(name)` — найти экран по имени, fallback на primary
- `format_screen_label(screen)` — форматирование строки для combo box

### 9. Детекция фиксаций — `fixation.py`

**`FixationDetector`** — обнаруживает фиксации взгляда в реальном времени на потоке gaze-точек:

- Поддерживает скользящее **окно по числу отсчётов** (`window_size_samples`, по умолчанию 10): реализовано через `deque(maxlen=window_size_samples)` — старые точки вытесняются автоматически при превышении размера.
- По каждому обновлению вычисляет **центроид** (среднее x, y) и **максимальный радиус** (максимальное расстояние от центроида до любой точки в окне).
- Детекция начинается только после накопления не менее `min_points` точек.
- Фиксация **входит** когда `radius < k`.
- Фиксация **выходит** когда `radius > k × 1.2` (гистерезис для устойчивости к шуму).
- Callback `on_fixation(fixation_dict)` вызывается ровно один раз при переходе в состояние фиксации.

**Payload фиксации** (передаётся в callback):

```json
{
  "k": 80.0,
  "window_points": [{"x": 540, "y": 400}, ...],
  "center": {"x": 0.52, "y": 0.41},
  "radius": 12.3,
  "is_first": true,
  "emotion": "neutral",
  "time_ms": 1250
}
```

Поля `is_first`, `emotion`, `time_ms` и нормализация `center` до `[0, 1]` добавляются в `TestRunScreen._on_fixation_detected()` до записи в `RecordItemMetrics`.

**Параметры** (`__init__`):

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `k` | `float` | — | Порог радиуса в пикселях экрана |
| `window_size_samples` | `int` | `10` | Размер скользящего окна (в отсчётах) |
| `min_points` | `int` | `6` | Минимум точек в окне для детекции |
| `exit_hysteresis_factor` | `float` | `1.2` | Множитель гистерезиса выхода |

Методы:
- `reset()` — сбрасывает буфер и состояние (вызывается при смене изображения).
- `on_gaze_point(x, y)` — подаёт новую точку; NaN/inf игнорируются.

### 10. Распознавание эмоций — `face_emotion.py`

**`FaceEmotionRecognition`** — заглушка для распознавания эмоций пользователя в момент фиксации взгляда.

- `get_emotion_at(x, y) -> str` — возвращает случайно выбранный ярлык из набора: `neutral`, `happy`, `sad`, `angry`, `surprised`, `fear`, `disgust`.
- Принимает опциональный `rng: random.Random` для детерминированных результатов в тестах.
- Интерфейс спроектирован для последующей замены реальной моделью без изменения вызывающего кода.

### 11. Агрегация метрик взгляда — `metrics.py`

**`GazeMetricsAggregator`** — собирает точки взгляда во время показа изображения и группирует их:
- Нормализует пиксельные координаты в диапазон 0..1 относительно размера экрана
- Группирует по `k=1` точкам (каждая точка взгляда — отдельная группа)
- Для каждой группы вычисляет средний `x`, `y` и `count`
- Результат: `list[GazeGroup]` с полями `x`, `y`, `count`

### 12. Тепловая карта — `heatmap.py`

**`generate_heatmap(image_path, gaze_groups)`** — генерирует тепловую карту взгляда поверх изображения:
- Загружает исходное изображение через OpenCV
- Строит 2D карту плотности: Gaussian-блоб на каждую группу взгляда (вес пропорционален `count`)
- Нормализует карту плотности в диапазон 0..1
- Применяет цветовую карту `COLORMAP_JET` (синий→зелёный→красный)
- Смешивает с оригиналом: `alpha = density * 0.6` (нулевая плотность = оригинал виден полностью)
- Возвращает RGB uint8 `ndarray` того же размера, что и исходное изображение

**`save_heatmap(image_path, gaze_groups, output_path)`** — обёртка для сохранения в файл.

### 12.1. Карта фиксаций — `fixation_map.py`

**`generate_fixation_map(image_path, fixation, *, number=None)`** — рендерит одну фиксационную точку поверх изображения:
- Загружает исходное изображение через OpenCV
- Определяет координаты: если `center.x > 1` или `center.y > 1` — абсолютные пиксели (старые записи); иначе нормализованные `[0, 1]` (новые записи)
- Рисует полупрозрачный заливной круг (amber) + контурное кольцо
- Если передан `number` — рисует номер фиксации внутри круга вместо центральной точки
- Рисует тёмную подложку + текст эмоции над/под кругом
- Возвращает RGB uint8 `ndarray`

### 13. Экспорт отчётов — `report_export.py`

**`export_record_zip(record, save_path, test_dao, test_data)`** — создаёт ZIP-архив с результатами записи:
- `report.json` — полный JSON записи (все поля Record, включая items и metrics)
- Для каждого изображения — папка `image_N/`:
  - `original.<ext>` — оригинальное изображение
  - `heatmap.png` — тепловая карта взгляда
  - `metrics.json` — метрики для данного изображения
- Fallback: если `test_dao`/`test_data` не переданы или файл не найден — записывает только `image_N/metrics.json`

### 14. Форматирование времени — `time_fmt.py`

**`format_datetime(iso_str)`** — конвертирует ISO 8601 строку в человекочитаемый формат `DD.MM.YYYY HH:MM`. Обрабатывает timezone-aware строки (конвертирует в локальное время). При ошибке парсинга возвращает исходную строку.

### 15. Слой данных

Данные организованы в модули с разделением ABC-интерфейса и локальной реализации:

#### Тесты — `data/test/`

Абстрактный интерфейс `TestDao` (ABC) с методами `create`, `update`, `load_all`, `load`, `delete`, `get_cover_path`, `get_image_path`. Позволяет подменять реализацию (локальная ↔ удалённая).

**`LocalTestDao`** — реализация для локальной файловой системы:

```
~/.eyetracker/tests/
├── tests.json              # метаданные [{id, name, cover_filename, image_filenames}]
├── <uuid-1>/
│   ├── cover.jpg           # обложка (оригинальное расширение)
│   ├── 001.png             # изображения (нумерация + расширение)
│   └── 002.jpg
└── <uuid-2>/
    └── ...
```

При вызове `create()` файлы **копируются** из оригинального местоположения в директорию теста. Метаданные хранят только относительные имена файлов. При `update()` файлы сначала копируются во временную директорию (`<id>_tmp`), затем старая удаляется и tmp переименовывается — это позволяет безопасно обновлять тест, даже если источники указывают на файлы внутри самого теста.

#### Записи результатов — `data/record/`

Модели данных:
- **`Record`** — полная запись: `id`, `test_id`, `user_login`, `started_at`, `finished_at`, `duration_ms`, `items: list[RecordItem]`, `created_at`
- **`RecordItem`** — результат для одного изображения: `image_filename`, `image_index`, `metrics: RecordItemMetrics`
- **`RecordItemMetrics`** — метрики: `gaze_groups` (список групп взгляда с `x`, `y`, `count`); `fixations` (список фиксаций, по умолчанию `[]` — обратная совместимость со старыми записями); `first_fixation_time_ms` (время первой фиксации в мс от начала показа изображения, `None` для старых записей)
- **`RecordSummary`** — облегчённая версия Record без `items` (для списков)
- **`RecordQuery`** — параметры запроса: `test_id`, `user_login`, `date_from`, `date_to`, `page`, `page_size`

**`RecordService`** (ABC) — методы `save(record)`, `load(record_id)`, `query(query)`

**`LocalRecordService`** — хранит каждую запись как отдельный JSON-файл:
```
~/.eyetracker/records/<record_id>.json
```

Метод `query()` возвращает `RecordListResult` с `list[RecordSummary]` (без загрузки тяжёлых items/metrics). Поддерживает фильтрацию по `test_id`, `user_login`, диапазону дат и пагинацию.

#### Авторизация — `data/login/`

**`LoginService`** (ABC) — метод `login(login, password) -> str` (возвращает токен)

**`LocalLoginService`** — принимает любой login/password, возвращает заглушку токена. В будущем будет заменён на HTTP-реализацию.

#### Черновики — `data/draft_cache.py`

**`DraftCache`** — автосохранение незавершённых форм создания/редактирования теста в `~/.eyetracker/draft.json`. При следующем открытии приложения предлагает восстановить черновик. Хранит тип (`create`/`edit`), `test_id`, имя, обложку, список изображений.

### 16. Создание теста — UI

- **`CreateTestChoicePage`** (`create_test_page.py`) — две карточки: "Форма" (создание через UI) и "TEST.json" (заглушка)
- **`TestFormPage`** (`test_form_page.py`) — универсальная форма с тремя режимами (`FormMode.CREATE`, `VIEW`, `EDIT`):
  - **CREATE**: пустая форма, кнопка "Создать", запись через `TestDao.create()`
  - **VIEW**: pre-populated readonly, поля заблокированы, нет кнопки "+", кнопки действий: Пройти / Результаты / Редактировать / Выгрузить Json / Удалить
  - **EDIT**: pre-populated editable, кнопка "Сохранить", запись через `TestDao.update()`
- **Сигналы TestFormPage**: `back_requested`, `edit_requested`, `run_test_requested`, `results_requested`, `test_updated`, `test_deleted`, `test_created`
- **`ImageGridWidget`** (`image_grid.py`) — плиточная галерея с кнопкой "+" первой; плитки 16:9 (280×158), left-aligned, поддержка readonly режима:
  - **Drag-to-reorder**: Qt Native Drag & Drop (`QDrag` + `QMimeData`) для перестановки изображений в edit/create mode; полупрозрачный thumbnail при перетаскивании, подсветка целевой позиции
  - **Удаление**: красная кнопка "✕" в правом верхнем углу каждого тайла (edit/create mode)
  - **Превью**: клик по тайлу открывает `ImagePreviewOverlay` — полноэкранный тёмный оверлей с изображением на 70% ширины; закрытие по кнопке "✕", Esc, клику вне изображения
  - **Readonly**: в VIEW mode скрыты "+" и "✕", drag отключён, клик по тайлу открывает превью
- Валидация: inline (под каждым полем) + финальная при "Создать"/"Сохранить"
- File picker с фильтром `*.png *.jpg *.jpeg *.bmp *.gif *.webp` + пост-валидация через `QPixmap.isNull()`

### 17. Библиотека тестов — `test_library_page.py`

- **`TestLibraryPage`** — grid плиток со всеми тестами (обложка + название)
- Empty state при отсутствии тестов
- Клик по плитке → сигнал `test_selected(test_id)` → открытие в режиме просмотра
- `refresh()` — перезагрузка из DAO (вызывается при переключении на вкладку, после создания/удаления/редактирования)

### 18. Прохождение теста — `test_run_screen.py`

**`TestRunScreen`** — полноэкранный показ изображений теста с параллельным трекингом взгляда:
- Получает откалиброванный `EyeTracker` из `CalibrationScreen`
- Показывает изображения последовательно, каждое на заданное время
- Для каждого изображения собирает точки взгляда через `GazeMetricsAggregator` и запускает `FixationDetector`
- По завершении возвращает `get_results()` (список `(filename, aggregator)` пар) и `get_fixations()` (список фиксаций per-image)
- `App._build_record()` формирует `Record` из результатов и сохраняет через `RecordService`
- Параметр `show_gaze_marker` (bool): если включён, рисует красную точку (10px) в текущей позиции взгляда через `paintEvent`; размеры экрана кэшируются в `start()` на главном потоке для потокобезопасности

**Детекция фиксаций в `TestRunScreen`:**
- При `fixation_enabled=True` создаётся `FixationDetector` в `start()`; сбрасывается при каждой смене изображения.
- Каждая точка взгляда из `_on_gaze()` передаётся в `detector.on_gaze_point(x, y)` (тот же фоновый поток, что и агрегатор).
- При обнаружении фиксации вызывается `_on_fixation_detected()`:
  1. Устанавливает `is_first=True` только для первой фиксации в рамках текущего изображения.
  2. Записывает `time_ms` — время в мс от начала показа текущего изображения (`_image_started_at`).
  3. Вызывает `FaceEmotionRecognition.get_emotion_at()` и записывает результат в payload.
  4. Нормализует `center.x` и `center.y` в `[0, 1]` делением на `screen_w`/`screen_h`.
  5. Добавляет обогащённый dict в `_fixations_per_image[current_index]`.

**Параметры конструктора, связанные с фиксациями:**

| Параметр | Тип | По умолчанию | Источник |
|---|---|---|---|
| `fixation_enabled` | `bool` | `True` | `Settings.fixation_enabled` |
| `fixation_k` | `float` | `80.0` | `Settings.fixation_radius_threshold_k` |
| `fixation_window_samples` | `int` | `10` | `Settings.fixation_window_size_samples` |

### 19. История результатов — UI

#### Список записей — `records_list_page.py`

**`RecordsListPage`** — таблица записей для конкретного теста:
- `QTableWidget` с колонками: дата/время, пользователь, кнопка "Посмотреть отчет"
- Empty state: "Пока нет прохождений"
- Данные загружаются через `RecordService.query(RecordQuery(test_id=...))`
- Кнопка "← Назад" возвращает к странице теста

#### Детали записи — `record_detail_page.py`

**`RecordDetailPage`** — детальный просмотр одной записи:
- Заголовок: название теста, логин пользователя, дата/время
- **Горизонтальные табы** — кнопки с номерами изображений (1, 2, 3, ...). Клик по табу показывает тепловую карту выбранного изображения
- Область контента: `QScrollArea` — тепловая карта взгляда (960×540), ниже — интерактивный блок фиксаций:
  - Превью-изображение (960×540): при наведении на значок фиксации показывает точку фиксации через `generate_fixation_map()`
  - Сетка значков фиксаций (4 в ряд, центрированно): каждый значок 108×61 пикселей, показывает `#N emotion` и время обнаружения в мс; наведение обновляет превью
- При отсутствии исходного изображения (нет `test_dao` или файл не найден) — отображается сообщение об ошибке
- Кнопка **"Выгрузить отчет"** — `QFileDialog.getSaveFileName()` → `export_record_zip()` → ZIP-архив с папками per-image

---

## Навигация между экранами — `app.py`

Приложение использует два уровня `QStackedWidget`:

1. **`App._stack`** — верхний уровень (полноэкранные): HomeScreen ↔ CalibrationScreen ↔ TestRunScreen
2. **`HomeScreen._content_stack`** — внутренний (контент sidebar): страницы вкладок + динамически добавляемые detail/records/readiness страницы

Экраны:
- **HomeScreen** (`home.py`) — начальный экран с sidebar (macOS-стиль) и контентными страницами
- **CalibrationScreen** (`calibration.py`) — полноэкранная калибровка с QPainter
- **TestRunScreen** (`test_run_screen.py`) — полноэкранный показ изображений теста

### Sidebar (боковое меню)

Пункты sidebar в `home.py`:

| Пункт | ID | Описание |
|-------|----|----------|
| Обзор | `overview` | Логин-форма / дашборд (зависит от состояния авторизации) |
| Демо-трекер | `calibration` | Запуск калибровки (fullscreen) |
| Тесты | `tests` | Библиотека тестов (grid → просмотр → редактирование) |
| Создать тест | `create_test` | Создание теста через форму или TEST.json |
| Настройки | `settings` | Выбор монитора, пропуск калибровки |
| Помощь | `help` | FAQ со сворачиваемыми ответами |

Пункты кроме "Обзор" скрыты до авторизации.

### Dependency Injection

`App` создаёт зависимости и передаёт их вниз:
- `Settings` → `HomeScreen` (настройки монитора, авторизация)
- `LocalTestDao` → `HomeScreen` → `TestFormPage` / `TestLibraryPage` (хранение тестов)
- `LocalLoginService` → `HomeScreen` (авторизация)
- `LocalRecordService` → `HomeScreen` → `RecordsListPage` / `RecordDetailPage` (записи результатов)
- `DraftCache` → `HomeScreen` → `TestFormPage` (автосохранение черновиков)

Навигация через коллбеки:
- `HomeScreen.on_start_calibration` → `App._go_to_calibration()` — создаёт новый `EyeTracker` + `CalibrationScreen`
- `HomeScreen.on_start_test_run(test)` → `App._go_to_test_run()` — калибровка → `TestRunScreen` → сохранение `Record`
- `CalibrationScreen.on_back` → `App._go_to_home()` — останавливает и уничтожает `CalibrationScreen`

При каждом входе в калибровку создаётся **новый** `EyeTracker` и `CalibrationScreen` — полностью чистое состояние. При возврате на home экран калибровки уничтожается (`deleteLater()`), освобождая камеру и память.

### Прохождение теста — навигация

Flow через `App._stack`:
1. "Пройти" на странице теста → экран готовности ("Готовы начать?")
2. "Начать" → `CalibrationScreen` (fullscreen, с `on_finished` callback)
3. Калибровка завершена → `CalibrationScreen.stop_ui_only()` (UI останавливается, трекер сохраняется)
4. `TestRunScreen` получает откалиброванный трекер → последовательный показ изображений
5. Все изображения показаны → `App._build_record()` → `RecordService.save()` → возврат на home
6. `QMessageBox.information("Результат теста сохранён.")`

### Создание теста — навигация

Flow внутри `_content_stack` HomeScreen:
1. Sidebar → `CreateTestChoicePage` (две карточки: Форма / TEST.json)
2. Клик "Форма" → `TestFormPage(mode=CREATE)` добавляется в стек
3. "Назад" → возврат к `CreateTestChoicePage`, форма удаляется
4. "Создать" (успех) → файлы копируются через `TestDao.create()`, возврат к выбору

### Библиотека тестов — навигация

Flow внутри `_content_stack` HomeScreen:
1. Sidebar "Тесты" → `TestLibraryPage` (grid плиток, auto-refresh)
2. Клик по плитке → `TestFormPage(mode=VIEW)` — просмотр (readonly)
3. "Редактировать" → `TestFormPage(mode=EDIT)` — редактирование
4. "Сохранить" (успех) → `TestDao.update()`, остаётся на тесте в режиме VIEW
5. "Удалить" → confirm dialog, `TestDao.delete()`, возврат в библиотеку, refresh
6. "Выгрузить Json" → экспорт TEST.json через QFileDialog
7. "← Назад" → возврат в библиотеку, refresh

### История результатов — навигация

Flow внутри `_content_stack` HomeScreen:
```
TestFormPage(VIEW) → [Результаты] → RecordsListPage → [Посмотреть] → RecordDetailPage
                                         ↑ [Назад]                       ↑ [Назад]
                                     TestFormPage                    RecordsListPage
```

ESC-клавиша работает как "Назад" на каждом уровне вложенности.

### Тема оформления — `theme.py`

Централизованные константы стиля macOS (тёмная тема): цвета фона, текста, кнопок, ошибок, карточек, размеры sidebar, плиток галереи, шрифты. Глобальный stylesheet для `QMessageBox` с белым текстом на тёмном фоне задаётся в `app.py`.

## UI калибровки — `calibration.py`

Построен на PyQt6. `CalibrationScreen(QWidget)` — единый виджет с `paintEvent` для отрисовки через QPainter, `start()`/`stop()` для управления жизненным циклом.

Поддерживает два режима:
- **Демо-режим** — запускается из sidebar "Демо-трекер", по завершении возвращает на home
- **Тестовый режим** — запускается при прохождении теста, по завершении вызывает `on_finished` callback и передаёт трекер в `TestRunScreen`

Параметр `skip_calibration` пропускает фазу кликов по точкам (сразу переходит к measurement/gaze). При этом загружаются ранее сохранённые данные калибровки из `~/.eyetracker/calibration.json` — данные сохраняются автоматически по завершении реальной калибровки.

Метод `stop_ui_only()` останавливает UI (таймеры, видео), но сохраняет `EyeTracker` живым для передачи в `TestRunScreen`.

### Фазы работы

| Фаза | Описание |
|------|----------|
| `instructions` | Экран приветствия, клик для начала |
| `calibration` | 9 красных точек в сетке 3x3, по 5 кликов на каждую |
| `measurement` | Зелёная точка в центре, 5 секунд сбора данных |
| `gaze` | Красная точка предсказания взгляда, режим тренировки |

### Калибровка — 9 точек

Точки располагаются в сетке 3x3 с отступом 10% от краёв экрана:

```python
# calibration.py:263-271
margin_x = int(self.screen_width * 0.1)
margin_y = int(self.screen_height * 0.1)
positions = []
for row in range(3):
    for col in range(3):
        x = margin_x + col * (self.screen_width - 2 * margin_x) // 2
        y = margin_y + row * (self.screen_height - 2 * margin_y) // 2
        positions.append((x, y))
```

Центральная точка (#4) скрыта до завершения остальных 8. Каждый клик:
1. Находит ближайшую незавершённую точку в радиусе 60 пикселей
2. Вызывает `wg.record_screen_position(px, py, "click")` — записывает координаты + признаки глаз в регрессионную модель
3. Меняет цвет точки от красного к жёлтому по мере прогресса

### Режим динамической тренировки (Train Mode)

Активируется клавишей **T** в фазе `gaze`. В этом режиме каждый клик мышью по экрану записывает калибровочную точку:

```python
# calibration.py:235-237
elif self._phase == self.PHASE_GAZE and self._train_mode:
    self.wg.record_screen_position(x, y, "click")
    self._feedback_markers.append((float(x), float(y), time.time()))
```

Визуальная обратная связь:
- Зелёный бейдж "TRAIN MODE" под превью видео
- Зелёные точки в местах кликов, затухающие за 0.5 секунды

Модель регрессии обновляется автоматически — `RidgeWeightedReg.predict()` пересчитывает коэффициенты из ВСЕХ накопленных данных при каждом предсказании.

### Превью видео

Камера выводится в левом верхнем углу (200x150 пикселей) с наложением ландмарков лица:

```python
# calibration.py:360-383
def _update_video(self):
    while self._video_running:
        frame = self.wg.get_latest_frame()
        if frame is not None:
            preview = cv2.resize(frame, (200, 150))
            preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            landmarks = self.wg.get_latest_landmarks()
            if landmarks:
                h, w = frame.shape[:2]
                scale_x = 200 / w
                scale_y = 150 / h
                for lx, ly in landmarks[:468]:
                    px = int(lx * scale_x)
                    py = int(ly * scale_y)
                    cv2.circle(preview, (px, py), 1, (0, 255, 0), -1)
            h, w, ch = preview.shape
            bytes_per_line = ch * w
            self._video_image = QImage(
                preview.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
            ).copy()
        time.sleep(0.05)
```

Видео обновляется в отдельном daemon-потоке. `.copy()` на `QImage` необходим, чтобы данные пережили numpy-массив.

### Отрисовка

Весь рендеринг происходит в `paintEvent` через `QPainter`. Таймер `QTimer(33ms)` вызывает `update()` виджета ~30 раз в секунду, что запускает перерисовку.

---

## Тестирование

114 unit-тестов (`pytest`):

| Файл | Кол-во | Что проверяет |
|------|--------|---------------|
| `test_util.py` | 18 | DataWindow, Eye, grayscale, equalize_histogram, threshold, correlation, resize_eye, bound, KalmanFilter |
| `test_regression.py` | 5 | _ridge, _get_eye_feats, add_data/predict для RidgeWeightedReg |
| `test_blink.py` | 3 | Детекция моргания на серии кадров |
| `test_precision.py` | 4 | PrecisionCalculator: хранение точек, расчёт precision |
| `test_settings.py` | 9 | Settings: save/load, corrupted JSON fallback, default values, auth_token, skip_calibration, last_opened_test_id |
| `test_monitor.py` | 4 | resolve_screen, format_screen_label |
| `test_test_dao.py` | 15 | LocalTestDao: create, update, load_all, load, delete, corrupt JSON, уникальные ID |
| `test_create_test_form.py` | 6 | validate_form: пустое имя, нет обложки, нет изображений, множественные ошибки |
| `test_draft_cache.py` | 8 | DraftCache: save/load/clear, corrupted JSON, missing file |
| `test_login_service.py` | 3 | LocalLoginService: успешный логин, возврат токена |
| `test_metrics.py` | 5 | GazeMetricsAggregator: нормализация, группировка, пустые данные |
| `test_record_service.py` | 8 | LocalRecordService: save/load, query с фильтрами, RecordSummary, user_login |
| `test_heatmap.py` | 10 | _build_density: форма, пик, масштабирование, накопление, граничные координаты; generate_heatmap: форма, dtype, пустые группы, горячая точка, отсутствующий файл; save_heatmap: запись файла |
| `test_report_export.py` | 8 | ZIP fallback (только metrics.json), полная структура папок, содержимое metrics.json, корректность heatmap PNG, graceful fallback при отсутствии файла |
| `test_time_fmt.py` | 4 | format_datetime: ISO 8601, timezone, невалидная строка |
| `test_fixation.py` | 5 | FixationDetector: детекция фиксации, нет фиксации при разбросе, флаг первой фиксации, state machine / debounce, вытеснение точек из окна |

Запуск:
```bash
make test          # или poetry run pytest
make test-verbose  # или poetry run pytest -v
```

---

## CLI — `main.py`

Точка входа, зарегистрированная в `pyproject.toml` как скрипт `eyetracker`:

```python
# main.py:9-25
def main():
    parser = argparse.ArgumentParser(description="Отслеживание взгляда через веб-камеру")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    ...
    from eyetracker.app import App
    app = App()
    app.run()
```

Приложение запускается на Home-экране. Калибровка начинается по клику на кнопку или пункт sidebar.

---

## Настройка окружения

Команда `make setup` выполняет полную настройку с нуля:

```bash
make setup
```

Шаги:
1. **Установка Python 3.12** — через `brew install python@3.12` (macOS) или `winget install Python.Python.3.12` (Windows)
2. **Настройка Poetry** — `poetry env use <path-to-python3.12>`
3. **Установка зависимостей** — `poetry lock && poetry install`

Требования: Homebrew (macOS) или winget (Windows), Poetry.

Если Python 3.12 уже установлен, достаточно `make install`.

---

## Сборка в нативное приложение

Приложение собирается через PyInstaller в нативный исполняемый файл. Конфигурация сборки — `eyetracker.spec`.

```bash
make setup     # первоначальная настройка (или make install если Python уже есть)
make build     # сборка
```

### macOS — `dist/EyeTracker.app`

- Режим **onedir**: файлы живут внутри `.app` бандла, не требуется распаковка во временную директорию при каждом запуске — быстрый старт.
- После сборки выполняется ad-hoc подпись с `entitlements.plist` (`codesign --deep --force --sign -`).
- `entitlements.plist` содержит:
  - `com.apple.security.device.camera` — доступ к камере
  - `com.apple.security.cs.allow-unsigned-executable-memory` — для нативных библиотек mediapipe/opencv
  - `com.apple.security.cs.disable-library-validation` — отключение валидации библиотек
- `Info.plist` включает `NSCameraUsageDescription` — macOS покажет диалог запроса доступа к камере при первом запуске.
- Для камеры на macOS используется бэкенд `cv2.CAP_AVFOUNDATION` (задаётся явно в `pipeline.py`).

### Windows — `dist/EyeTracker.exe`

- Режим **onefile**: один исполняемый файл, извлекает зависимости во временную директорию.
- `console=False` — запуск без консольного окна.

### Что бандлится

- Пакет `mediapipe` целиком (нативные библиотеки, конфиги)
- Модель `face_landmarker.task` из `eyetracker/models/` (если была скачана до сборки)
- Hidden imports: mediapipe, numpy, cv2, PyQt6

### Путь к модели в бандле

В `pipeline.py` путь к модели определяется с учётом PyInstaller:

```python
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
_MODEL_DIR = os.path.join(_BASE_DIR, "eyetracker", "models") if hasattr(sys, "_MEIPASS") else os.path.join(os.path.dirname(__file__), "models")
```

Если модель не найдена, она скачивается автоматически при первом запуске.
