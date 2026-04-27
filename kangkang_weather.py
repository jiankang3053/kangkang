# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

from wechat_weather.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["tray"]))
