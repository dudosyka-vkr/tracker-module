# Технический долг

## 2. ROI не сохраняются при создании теста

**Файл:** форма создания/редактирования теста

**Проблема:** ROI, нарисованные в редакторе теста, не сохраняются — после создания теста они отсутствуют.

---

## 1. Переключение монитора на macOS — hardcoded delay

**Файл:** `eyetracker/app.py:_move_to_target_screen()`

**Проблема:** macOS fullscreen exit анимирован и полностью асинхронен. Qt-сигнал `windowStateChanged` и поллинг `isFullScreen()` срабатывают до того, как macOS реально завершает анимацию и позволяет переместить окно на другой монитор. В результате `setGeometry()` / `move()` не работают — окно остаётся на текущем мониторе.

**Текущее решение:** `QTimer.singleShot(1000, ...)` — hardcoded задержка 1 секунда после `showNormal()`. Работает, но:
- Может быть недостаточно, если пользователь увеличил длительность анимаций в System Settings → Accessibility
- Избыточно на быстрых системах

**Что пробовали:**
- `windowHandle().windowStateChanged` signal — срабатывает до завершения анимации
- Поллинг `isFullScreen()` каждые 50ms + 100ms delay — `isFullScreen()` возвращает `False` до реального завершения
- `move()` + `processEvents()` + `resize()` — macOS не перемещает окно между мониторами

**Возможные решения для исследования:**
- Использовать Cocoa API напрямую через `pyobjc` (NSWindow `toggleFullScreen:` + наблюдатель `NSWindowDidExitFullScreenNotification`)
- Не использовать macOS native fullscreen — вместо `showFullScreen()` делать `setWindowFlags(Qt.FramelessWindowHint)` + `setGeometry(screen.geometry())` (frameless maximized window, не задействует macOS fullscreen animation)
- Попробовать `QWindow.setScreen()` до вызова `showFullScreen()` без промежуточного `showNormal()`
