"""Main entry point for the eye tracker desktop application."""

from __future__ import annotations

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(description="Отслеживание взгляда через веб-камеру")
    parser.add_argument("--camera", type=int, default=0, help="Индекс камеры (по умолчанию: 0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробное логирование")
    parser.add_argument("--dev", action="store_true", help="Режим разработки: все логи включены")
    args = parser.parse_args()

    if getattr(sys, "frozen", False):
        logging.disable(logging.CRITICAL)
    else:
        level = logging.DEBUG if (args.dev or args.verbose) else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    from eyetracker.app import App

    app = App()
    app.run()


if __name__ == "__main__":
    main()
