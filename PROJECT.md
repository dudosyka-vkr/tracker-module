# Документация проекта EyeTracker

## Структура проекта

```
eyetracker/
├── pyproject.toml                         # Конфигурация Poetry, зависимости
├── Makefile                               # Команды: install, run, test, clean
├── eyetracker/
│   ├── __init__.py                        # Версия пакета
│   ├── main.py                            # CLI точка входа (argparse)
│   ├── pipeline.py                        # Трекер, детекция моргания, регрессия, оркестратор
│   ├── calibration.py                     # UI калибровки (PyQt6) + измерение точности
│   ├── util.py                            # Eye, DataWindow, KalmanFilter, обработка изображений
│   └── models/                            # Автоматически скачиваемая модель (face_landmarker.task)
└── tests/
    ├── test_util.py                       # 18 тестов
    ├── test_regression.py                 # 5 тестов
    ├── test_blink.py                      # 3 теста
    └── test_precision.py                  # 4 теста
```

## Зависимости

| Пакет | Назначение |
|-------|-----------|
| `numpy` | Матричные операции, линейная алгебра |
| `opencv-python` | Захват видео, обработка изображений |
| `mediapipe` | Детекция лица и ландмарков (FaceLandmarker) |
| `PyQt6` | GUI калибровки и отслеживания |

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

---

## UI калибровки — `calibration.py`

Построен на PyQt6. Состоит из кастомного виджета `_CalibrationWidget` (обрабатывает отрисовку, клики и клавиатуру) и класса `CalibrationApp` (управляет состоянием).

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

30 unit-тестов (`pytest`):

| Файл | Кол-во | Что проверяет |
|------|--------|---------------|
| `test_util.py` | 18 | DataWindow, Eye, grayscale, equalize_histogram, threshold, correlation, resize_eye, bound, KalmanFilter |
| `test_regression.py` | 5 | _ridge, _get_eye_feats, add_data/predict для RidgeWeightedReg |
| `test_blink.py` | 3 | Детекция моргания на серии кадров |
| `test_precision.py` | 4 | PrecisionCalculator: хранение точек, расчёт precision |

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
    parser = argparse.ArgumentParser(description="Eye tracking via webcam")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    ...
    app = CalibrationApp(EyeTracker())
    app.run()
```

Сглаживание Калмана, детекция моргания и взвешенная гребневая регрессия включены по умолчанию.
