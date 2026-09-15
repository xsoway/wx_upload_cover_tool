#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2026/1/10 15:38
# @Filename : config_loader.py


import configparser
from pathlib import Path
from typing import Tuple, Optional


_CONFIG_CACHE = None


def _load_config() -> configparser.ConfigParser:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    # 优先读取本工具自带的 config/config.ini（自包含部署）
    tool_root = Path(__file__).resolve().parents[2]
    candidate_paths = [
        tool_root / "config" / "config.ini",
        Path("config/config.ini"),
        Path("../config/config.ini"),
    ]

    cfg = configparser.ConfigParser()
    for p in candidate_paths:
        if p.exists():
            cfg.read(p, encoding="utf-8")
            _CONFIG_CACHE = cfg
            return cfg

    raise FileNotFoundError(
        "未找到 config.ini，请确保存在 config/config.ini"
    )


def get_wechat_config() -> Tuple[str, str]:
    """
    返回 (appid, secret)
    """
    cfg = _load_config()
    appid = cfg.get("wechat", "appid", fallback="").strip()
    secret = cfg.get("wechat", "secret", fallback="").strip()

    if not appid or not secret:
        raise RuntimeError("config.ini 中 [wechat] appid / secret 未配置")

    return appid, secret


def get_github_token() -> Optional[str]:
    cfg = _load_config()
    token = cfg.get("github", "token", fallback="").strip()
    return token or None