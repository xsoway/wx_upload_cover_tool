#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2026/1/31 12:10
# @Filename : core.py

"""
功能（极简版）：
1) 基于 HTML 模板 + Playwright 注入两段文字生成公众号封面图
2) 将封面规范化为微信更稳的 JPEG
3) 上传到公众号素材库（永久素材 image），返回 media_id + url
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

from wxcover.logger import GetLogger
from wxcover.config_loader import get_wechat_config

logger = GetLogger.get_logger("wx_upload_cover_tool")

WECHAT_API = "https://api.weixin.qq.com"

# 工具根目录（保证任意工作目录下都能找到模板/输出）
TOOL_ROOT = Path(__file__).resolve().parents[2]

# 可选的标题（公众号封面下拉，公开通用占位）
TITLE_OPTIONS = [
    "我的分享",
    "技术随笔",
    "项目复盘",
    "工具推荐",
    "学习笔记",
    "经验总结",
    "行业观察",
    "思考手记",
]
DEFAULT_TITLE_TEXT = TITLE_OPTIONS[0]
DEFAULT_HTML_FILE = "minimal.html"

# 可选封面模板：名称 -> 模板文件名（公开样式）
TEMPLATES = {
    "极简": "minimal.html",
    "深空": "cosmic.html",
    "暖纸": "paper.html",
    "霓虹": "neon.html",
    "清新": "fresh.html",
}
DEFAULT_TEMPLATE = "极简"


def _resolve(path: str) -> Path:
    """把 path 解析为绝对路径；相对路径基于工具根目录。"""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (TOOL_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


# =========================
# 封面图：Playwright 生成（HTML 模板 + 注入两段文字）
# =========================

def render_cover_image_by_html(
    title_text: str,
    subtitle_text: str,
    html_file: str,
    out_dir: str,
    out_name: Optional[str] = None,
    w: int = 900,
    h: int = 383,
    scale: int = 2,
    title_id: str = "title",
    subtitle_id: str = "subtitle",
    swap_title_subtitle: bool = False,
    nav_timeout_ms: int = 120000,
    warmup_ms: int = 800,
    wait_ms: int = 300,
) -> str:
    """用 Playwright 渲染本地 HTML 模板，并注入两段文字生成封面 PNG"""
    # 模板统一存放在 templates/ 下：裸文件名优先按 templates/ 解析，绝对路径直接使用
    html_path = Path(html_file)
    if not html_path.is_absolute():
        html_path = _resolve(TOOL_ROOT / "templates" / html_file)
    else:
        html_path = html_path.resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    out_dir_path = _resolve(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_name = out_name or f"wechat_cover_{date_str}.png"
    out_path = out_dir_path / out_name

    logger.info(
        "🖼️ 生成封面图(HTML) | title=%s | subtitle=%s | html=%s | out=%s",
        title_text, subtitle_text, str(html_path), str(out_path)
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": w, "height": h},
            device_scale_factor=scale
        )

        page.goto(
            html_path.as_uri(),
            wait_until="domcontentloaded",
            timeout=nav_timeout_ms
        )
        page.wait_for_timeout(warmup_ms)

        # 等字体就绪（如果支持）
        page.evaluate("""() => (document.fonts && document.fonts.ready) ? document.fonts.ready : true""")

        # 是否互换 标题值 <-> 副标题值（用于突出副标题）
        title_value = subtitle_text if swap_title_subtitle else title_text
        sub_value = title_text if swap_title_subtitle else subtitle_text

        # 注入标题
        page.evaluate(
            """([id, value]) => {
              const el = document.getElementById(id);
              if (el) {
                el.textContent = value ?? "";
                el.style.display = "";
              }
            }""",
            [title_id, title_value]
        )

        # 注入副标题
        page.evaluate(
            """([id, value]) => {
              const el = document.getElementById(id);
              if (!el) return;
              const v = (value ?? "").trim();
              if (!v) {
                el.textContent = "";
                el.style.display = "none";
              } else {
                el.textContent = v;
                el.style.display = "";
              }
            }""",
            [subtitle_id, sub_value]
        )

        # ✅ 出图模式（配合 HTML 里的 body.export）
        page.evaluate("document.body.classList.add('export')")

        # ✅ 注入文字后让模板执行一次自适应排版（标题/副标题缩放、眉题拆分等）
        page.evaluate("() => { try { window.__coverAfterText__ && window.__coverAfterText__(); } catch (e) {} }")

        # ✅ 强制触发一次重排（字体/CSS/脚本更稳定）
        page.evaluate("() => { window.dispatchEvent(new Event('resize')); }")

        # ✅ 禁用动画/过渡，避免截屏瞬间状态变化
        page.add_style_tag(content="*{transition:none!important;animation:none!important;}")

        # ✅ 等到 .stage 尺寸稳定（比纯 sleep 更可靠）
        page.wait_for_function(
            """() => {
              const el = document.querySelector('.stage');
              if (!el) return false;
              const r = el.getBoundingClientRect();
              return r.width >= 899 && r.height >= 382;
            }""",
            timeout=5000
        )

        page.wait_for_timeout(wait_ms)

        # 更稳：优先截 .stage
        locator = page.locator(".stage")
        if locator.count() > 0:
            locator.screenshot(path=str(out_path), omit_background=False)
        else:
            page.screenshot(
                path=str(out_path),
                clip={"x": 0, "y": 0, "width": w, "height": h},
                omit_background=False
            )

        browser.close()

    logger.success("✅ 封面图已生成 | path=%s", str(out_path))
    return str(out_path)


# =========================
# 封面图：规范化（微信上传更稳）
# =========================

def normalize_cover_for_wechat(src_path: str, out_path: str) -> str:
    """
    微信上传更稳：RGB + JPEG + 合理质量
    """
    p = Path(src_path)
    if not p.exists():
        raise FileNotFoundError(f"封面图不存在: {src_path}")

    img = Image.open(str(p))
    img.load()

    if img.mode != "RGB":
        img = img.convert("RGB")

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    img.save(str(out_p), format="JPEG", quality=92, optimize=True)
    logger.success(
        "✅ 封面图已规范化为 JPEG | out=%s | bytes=%d",
        str(out_p), out_p.stat().st_size
    )
    return str(out_p)


# =========================
# 微信 API：token / 上传素材
# =========================

def get_access_token(appid: str, secret: str) -> str:
    url = f"{WECHAT_API}/cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": appid, "secret": secret}
    logger.info("获取 access_token | appid_prefix=%s***", (appid or "")[:6])
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"获取 access_token 失败: {data}")
    logger.success("access_token ok")
    return data["access_token"]


def upload_cover_image(access_token: str, image_path: str) -> Tuple[str, str]:
    """
    上传永久素材（image），返回 (media_id, url)
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"封面图不存在: {image_path}")

    url = f"{WECHAT_API}/cgi-bin/material/add_material"
    params = {"access_token": access_token, "type": "image"}

    logger.info("上传封面图 | path=%s", image_path)
    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/jpeg")}
        resp = requests.post(url, params=params, files=files, timeout=120)

    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"上传封面图失败: {data}")

    media_id = data["media_id"]
    img_url = data.get("url") or ""
    logger.success("封面上传成功 | media_id=%s | url=%s", media_id, img_url)
    return media_id, img_url


# =========================
# 主流程：只上传封面
# =========================

@dataclass
class CoverUploadResult:
    ok: bool
    src_path: str = ""
    normalized_path: str = ""
    media_id: str = ""
    url: str = ""
    error: str = ""


def upload_only_cover(
    appid: str,
    secret: str,
    image_path: str,
    out_dir: str = "outputs/wx_cover_upload",
    normalize: bool = True,
) -> CoverUploadResult:
    try:
        image_path = str(Path(image_path))
        if not Path(image_path).exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        normalized_path = image_path
        if normalize:
            date_str = datetime.now().strftime("%Y-%m-%d")
            out_dir = Path(out_dir) / date_str
            out_dir.mkdir(parents=True, exist_ok=True)
            normalized_path = str(out_dir / (Path(image_path).stem + "_wechat.jpg"))
            normalized_path = normalize_cover_for_wechat(image_path, normalized_path)

        token = get_access_token(appid, secret)
        media_id, url = upload_cover_image(token, normalized_path)

        return CoverUploadResult(
            ok=True,
            src_path=image_path,
            normalized_path=normalized_path,
            media_id=media_id,
            url=url,
        )
    except Exception as e:
        logger.exception("❌ 仅封面上传失败")
        return CoverUploadResult(ok=False, src_path=image_path, error=str(e))


# =========================
# 主流程：生成封面(HTML) -> 规范化 -> 上传
# =========================

def generate_and_upload_cover(
    title_text: str,
    subtitle_text: str,
    html_file: str = DEFAULT_HTML_FILE,
    template: Optional[str] = None,
    swap_title_subtitle: bool = False,
    generated_dir: str = "outputs/generated_cover_html",
    upload_dir: str = "outputs/wx_cover_upload",
    normalize: bool = True,
    upload: bool = True,
) -> CoverUploadResult:
    """
    根据 标题 + 副标题 生成封面并上传。
    - template: 模板名称（见 TEMPLATES），例如 "极简"；
                优先于 html_file。为 None 时使用 html_file。
    - swap_title_subtitle: 为 True 时互换 标题值 与 副标题值（用于突出副标题）
    - upload=True 时生成并上传到公众号素材库
    - upload=False 仅生成封面图（本地），不执行上传
    """
    if template:
        fname = TEMPLATES.get(template)
        if not fname:
            return CoverUploadResult(ok=False, error=f"未知模板: {template}")
        html_file = fname

    title_text = (title_text or "").strip()
    subtitle_text = (subtitle_text or "").strip()
    if not title_text:
        return CoverUploadResult(ok=False, error="标题不能为空")

    try:
        png = render_cover_image_by_html(
            title_text=title_text,
            subtitle_text=subtitle_text,
            html_file=html_file,
            out_dir=generated_dir,
            w=900,
            h=383,
            scale=2,
            title_id="title",
            subtitle_id="subtitle",
            swap_title_subtitle=swap_title_subtitle,
        )

        if not upload:
            return CoverUploadResult(ok=True, src_path=png, normalized_path=png)

        appid, secret = get_wechat_config()
        res = upload_only_cover(
            appid,
            secret,
            png,
            out_dir=upload_dir,
            normalize=normalize,
        )
        res.src_path = res.src_path or str(png)
        return res
    except Exception as e:
        logger.exception("❌ 生成/上传封面失败")
        return CoverUploadResult(ok=False, error=str(e))


# =========================
# 本地直接运行：生成封面(HTML) -> 上传
# =========================

def main():
    """命令行入口：生成一张示例封面并上传（未配置凭据时仅本地生成）。"""
    title_text = "示例标题"
    subtitle_text = "示例副标题：一句话说明这篇文章讲了什么"

    res = generate_and_upload_cover(
        title_text=title_text,
        subtitle_text=subtitle_text,
        upload=True,
    )
    print(res)


if __name__ == "__main__":
    main()

