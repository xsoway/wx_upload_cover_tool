#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2026/1/31 12:10
# @Filename : __init__.py
"""
公众号封面生成工具 wxcover。

核心能力：
- render_cover_image_by_html     : HTML 模板 + Playwright 渲染封面
- normalize_cover_for_wechat     : 规范化 JPEG（微信上传更稳）
- generate_and_upload_cover      : 生成 -> 规范化 -> 上传 主流程
"""

from wxcover.core import (
    render_cover_image_by_html,
    normalize_cover_for_wechat,
    generate_and_upload_cover,
    upload_only_cover,
    CoverUploadResult,
    TEMPLATES,
    TITLE_OPTIONS,
)

__all__ = [
    "render_cover_image_by_html",
    "normalize_cover_for_wechat",
    "generate_and_upload_cover",
    "upload_only_cover",
    "CoverUploadResult",
    "TEMPLATES",
    "TITLE_OPTIONS",
]

__version__ = "0.2.0"