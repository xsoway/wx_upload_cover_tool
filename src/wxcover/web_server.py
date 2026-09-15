#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
公众号封面生成 - Web 前端后端
特性：
- TITLE_TEXT 下拉选择
- SUBTITLE_TEXT 输入框
- 提交后实时流式输出日志、结果
纯标准库实现（ThreadingHTTPServer），把工具运行日志实时推给浏览器。
"""

from __future__ import annotations

import io
import json
import logging
import sys
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from queue import Queue, Empty

import wxcover.core as tool

BASE_DIR = Path(__file__).resolve().parents[2]
HTML_FILE = BASE_DIR / "static" / "index.html"
HOST = "127.0.0.1"
PORT = 8765


# ---------------------------------------------------------------------------
# 日志实时管道：把日志记录和标准输出都转发到一个队列
# ---------------------------------------------------------------------------
class QueueHandler(logging.Handler):
    """把 logging 记录格式化成一行文本后塞进队列。"""

    def __init__(self, queue: Queue) -> None:
        super().__init__(level=logging.DEBUG)
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.queue.put(msg)
        except Exception:
            traceback.print_exc()


def _run_pipeline(payload: dict, queue: Queue) -> dict:
    """在调用方线程中执行 生成+上传，并把日志实时写入 queue。"""
    logger = logging.getLogger("wx_upload_cover_tool")

    handler = QueueHandler(queue)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s][%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)

    # 转发标准输出（print 的输出），保证信息尽量完整
    old_stdout = sys.stdout
    printed = io.StringIO()

    def flush_printed():
        value = printed.getvalue()
        if value:
            for line in value.splitlines():
                if line.strip():
                    queue.put(line)
            printed.seek(0)
            printed.truncate(0)

    try:
        sys.stdout = printed
        title = (payload.get("title") or "").strip()
        subtitle = (payload.get("subtitle") or "").strip()
        upload = bool(payload.get("upload", True))
        template = (payload.get("template") or "").strip() or None
        swap = bool(payload.get("swap_title_subtitle", False))

        queue.put(
            f"▶️ 开始任务 title={title!r} subtitle={subtitle!r} "
            f"模板={template or tool.DEFAULT_TEMPLATE} 互换={swap} 是否上传={upload}"
        )
        result = tool.generate_and_upload_cover(
            title_text=title,
            subtitle_text=subtitle,
            template=template,
            swap_title_subtitle=swap,
            upload=upload,
        )
        flush_printed()

        summary = "🎉 完成 → ok=%s" % result.ok
        if result.media_id:
            summary += " | media_id=%s" % result.media_id
        if result.url:
            summary += " | url=%s" % result.url
        if not result.ok and result.error:
            summary += " | error=%s" % result.error
        queue.put(summary)

        return {
            "ok": result.ok,
            "src_path": result.src_path,
            "normalized_path": result.normalized_path,
            "media_id": result.media_id,
            "url": result.url,
            "error": result.error,
        }
    except Exception as e:  # noqa: BLE001
        queue.put("❌ 任务异常: %s" % e)
        traceback.print_exc()
        return {"ok": False, "error": str(e)}
    finally:
        sys.stdout = old_stdout
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# HTTP 请求处理
# ---------------------------------------------------------------------------
class WebHandler(BaseHTTPRequestHandler):
    server_version = "WxCoverWeb/1.0"

    def log_message(self, fmt, *args):
        return  # 静默访问日志

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._serve_html()
            return
        if parsed.path == "/api/title-options":
            self._send_json({
                "title_options": tool.TITLE_OPTIONS,
                "default_title": tool.DEFAULT_TITLE_TEXT,
                "templates": list(tool.TEMPLATES.keys()),
                "default_template": tool.DEFAULT_TEMPLATE,
            })
            return
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "请求体不是合法 JSON"},
                            status=HTTPStatus.BAD_REQUEST)
            return

        # 流式响应
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        queue: Queue = Queue()
        result_box = {}

        def work():
            result_box["result"] = _run_pipeline(payload, queue)
            # 哨兵：任务结束
            queue.put(None)

        threading.Thread(target=work, daemon=True).start()

        try:
            while True:
                try:
                    msg = queue.get(timeout=60)
                except Empty:
                    # 超时无输出，结束流
                    break
                if msg is None:
                    break
                line = (msg.rstrip() + "\n").encode("utf-8", "replace")
                try:
                    self.wfile.write(line)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            # 结束时追加一行 JSON 结果，便于前端获取最终结构化结果
            result = result_box.get("result")
            if result is not None:
                trailer = "\n__RESULT__ " + json.dumps(result, ensure_ascii=False) + "\n"
                try:
                    self.wfile.write(trailer.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        except Exception:
            return

    # -- helpers --
    def _serve_html(self):
        data = HTML_FILE.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict, status=HTTPStatus.OK):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = ThreadingHTTPServer((HOST, PORT), WebHandler)
    # flush=True 保证非交互/管道环境下也能立即显示提示，避免“看起来没输出”
    print(f"⚠️  公众号封面工具已启动:  http://{HOST}:{PORT}", flush=True)
    print("   按 Ctrl+C 退出", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()