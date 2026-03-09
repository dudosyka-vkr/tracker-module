"""Main entry point for the eye tracker desktop application."""

from __future__ import annotations

import argparse
import logging


def main():
    parser = argparse.ArgumentParser(description="Отслеживание взгляда через веб-камеру")
    parser.add_argument("--camera", type=int, default=0, help="Индекс камеры (по умолчанию: 0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробное логирование")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from eyetracker.pipeline import EyeTracker
    from eyetracker.calibration import CalibrationApp

    app = CalibrationApp(EyeTracker())
    app.run()


if __name__ == "__main__":
    main()
