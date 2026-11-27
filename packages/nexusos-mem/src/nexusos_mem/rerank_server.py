#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nexus.rerank_server — 常驻 bge-reranker-v2-m3 cross-encoder 精排 worker。

Task 458：NEXUS MEM RAG 改进三件套 Task 2。
照搬 embed_server.py 模板，砍掉 FSEvents 相关（rerank 是无状态请求，不需文件监控）。

设计（稳定性优先）:
    - 只绑 127.0.0.1（不暴露公网）
    - 启动即 warmup（compute_score 一次），首个真实请求不卡
    - 进程内锁串行化，避免 MPS 并发争用崩溃
    - 输入截断到 500 字符（reranker max_length 512 token）
    - 由 launchd KeepAlive 托管（ai.nexus.rerank.plist）
    - 失败不泄漏 traceback，统一 500 {"error": "..."}

端点:
    GET  /health           → {"status":"ok","ready":bool,"model":...,"scored":N}
    POST /rerank {"query":"...", "documents":[...], "top_n":N}
                           → {"results":[{"index":i,"score":f,"document":"..."}], "model":...}

加载方式：
    优先 FlagModel（BGE 官方推荐，接口简洁），fallback transformers AutoModel。
    两种 API 不同：
      FlagModel: model.compute_score([[q,d1],[q,d2]]) → list[float]
      AutoModel: tokenizer(q,d) → model forward → logits → softmax → score

用法:
    python3 -m nexus.rerank_server                 # 默认 127.0.0.1:11437
    NEXUS_RERANK_PORT=11500 python3 -m nexus.rerank_server
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 离线，避免每次推理触发 HF Hub 网络探测
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# 防自我递归（rerank_server 内部不会再调 :11437）
os.environ["NEXUS_RERANK_NO_WORKER"] = "1"

DEFAULT_HOST = os.environ.get("NEXUS_RERANK_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("NEXUS_RERANK_PORT", "11437"))

RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
# 2611269944：文本长度与最大 token 改成 env 可注入（按实测定；缺省保持原来的 500/512）。
MAX_DOC_CHARS = int(os.environ.get("NEXUS_RERANK_MAX_DOC_CHARS", "500"))
MAX_LEN = int(os.environ.get("NEXUS_RERANK_MAX_LEN", "512"))

_RERANK_LOCK = threading.Lock()
# 1635(#213 软挂根治)：锁获取超时熔断——持锁线程楔死在 MPS 调用上时，新请求快速失败
# 而非无限排队（把"永不返回"变"可观测失败"，楔死线程清场留给 watchdog 重启）。env 可注入。
#
# 2611269944：等锁上限从 120s 改成 **0.3s**，并把「忙」和「坏」分开：
#   服务端串行是物理约束，排队不是故障——等不到就立刻回 429「忙」+ Retry-After，
#   客户端收到「忙」只降级这一次（不冷却）。这样五路并发里最多一路真做重排，其余立刻返回，
#   没有一路把时间耗在排队上，也没有一路被误判成故障。
_LOCK_TIMEOUT = float(os.environ.get("NEXUS_RERANK_BUSY_WAIT",
                                    os.environ.get("NEXUS_RERANK_LOCK_TIMEOUT", "0.3")))
_RETRY_AFTER_SEC = int(os.environ.get("NEXUS_RERANK_RETRY_AFTER", "1"))
# 2611269944：保温（冷启动第一次为什么慢量出来后定的处置；0=不做）
_KEEPWARM_SEC = float(os.environ.get("NEXUS_RERANK_KEEPWARM_SEC", "300"))
_STATE = {"ready": False, "scored": 0, "started": time.time(), "model": RERANKER_MODEL_NAME,
          "lock_wait_ms": round(_LOCK_TIMEOUT * 1000, 1), "keepwarm_sec": _KEEPWARM_SEC,
          "keepwarm_runs": 0, "keepwarm_last_ms": None, "busy_rejects": 0, "train_time_ms": None}

# 模型懒加载（两种后端：FlagModel 优先，transformers AutoModel fallback）
_MODEL_CACHE = {"backend": None, "model": None, "tokenizer": None}


class BusyError(Exception):
    """2611269944：等锁超时＝「忙」，不是故障（客户端据此只降级这一次，不冷却）。"""


def _load_model():
    """加载 reranker 模型。优先 FlagReranker（BGE 官方推荐），fallback AutoModel。

    Returns: (backend, model, tokenizer) — tokenizer 仅 AutoModel 后端用

    注意：FlagEmbedding >=1.3 用 FlagReranker（不是 FlagModel，FlagModel 是 bi-encoder）。
    FlagReranker.compute_score([[q,d1],[q,d2]]) → list[float] 或 float（单对）。
    """
    if _MODEL_CACHE["model"] is not None:
        return _MODEL_CACHE["backend"], _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

    # 尝试 1: FlagReranker（BGE 官方 cross-encoder）
    try:
        import torch
        if not torch.cuda.is_available():
            # Task 562: FlagReranker 在 CPU 设备强制 fp32 加载（BaseReranker 源码
            # `if device == "cpu": self.use_fp16 = False`，且 from_pretrained 不收
            # torch_dtype）——先 fp32 物化再 half() 的峰值页留在 footprint（实测
            # 3956MB）。Mac 无 CUDA → 走下方 automodel 分支直接 fp16 加载（零 fp32 峰值）。
            raise RuntimeError("CPU 设备跳过 FlagReranker（fp32 物化内存超 Task562 预算）")
        from FlagEmbedding import FlagReranker
        print(f"[rerank_server] 加载 {RERANKER_MODEL_NAME} via FlagReranker...", flush=True)
        t0 = time.time()
        model = FlagReranker(
            RERANKER_MODEL_NAME,
            use_fp16=True,
        )
        print(f"[rerank_server] FlagReranker 加载完成 ({time.time()-t0:.1f}s)", flush=True)
        _MODEL_CACHE.update({"backend": "flagreranker", "model": model, "tokenizer": None})
        return "flagreranker", model, None
    except ImportError:
        print("[rerank_server] FlagEmbedding 未装，fallback 用 transformers AutoModel", flush=True)
    except Exception as e:
        print(f"[rerank_server] FlagReranker 加载失败 ({e})，fallback 用 AutoModel", flush=True)

    # 尝试 2: transformers AutoModelForSequenceClassification
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    print(f"[rerank_server] 加载 {RERANKER_MODEL_NAME} via AutoModel...", flush=True)
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(RERANKER_MODEL_NAME)
    # Task 562: fp32 加载 → 上 MPS → half()。不能 from_pretrained(torch_dtype=
    # float16) + .to(mps)——新版 transformers 在 dtype 直载下产 meta 初始化
    # 权重，跨设备拷贝报 "Cannot copy out of meta tensor"（实测 warmup 循环
    # 崩溃）。fp32 物化后 to+half 一次成型；fp32 峰值页由 warmup 后
    # gc+empty_cache 释放（见 _warmup）。
    model = AutoModelForSequenceClassification.from_pretrained(RERANKER_MODEL_NAME)
    _device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(_device).half() if _device == "mps" else model.half()
    model.eval()
    print(f"[rerank_server] AutoModel 加载完成 ({time.time()-t0:.1f}s, fp16@{_device})", flush=True)
    _MODEL_CACHE.update({"backend": "automodel", "model": model, "tokenizer": tokenizer})
    return "automodel", model, tokenizer


def _compute_scores(query: str, documents: list) -> list:
    """对每个 (query, doc) 对计算相关性分数。返回 list[float]，长度同 documents。

    串行化（_RERANK_LOCK），防 MPS 并发崩溃。
    """
    if not documents:
        return []
    # 截断
    docs = [(d or "")[:MAX_DOC_CHARS] for d in documents]
    backend, model, tokenizer = _load_model()

    # 1635：带超时获取锁——acquired=False 即持锁线程楔死/长尾，抛 TimeoutError 由
    # do_POST 统一转 503（api_server 既有重试+冷却链衔接；原 with 无限等待是软挂放大器）
    acquired = _RERANK_LOCK.acquire(timeout=_LOCK_TIMEOUT)
    if not acquired:
        _STATE["busy_rejects"] += 1
        print(f"[rerank_server] BUSY 等锁超过 {_LOCK_TIMEOUT * 1000:.0f}ms（排队中，非故障）"
              f"scored={_STATE['scored']} busy_rejects={_STATE['busy_rejects']}", file=sys.stderr, flush=True)
        raise BusyError(f"rerank busy: 等锁超过 {_LOCK_TIMEOUT * 1000:.0f}ms")
    try:
        return _infer(query, docs, backend, model, tokenizer)
    finally:
        # 1635：手动 acquire 必配 finally 归还（还原原 with 的异常安全语义——任何退出路径含异常都释放）
        _RERANK_LOCK.release()


def _infer(query, docs, backend, model, tokenizer):
    """真正的模型推理（**不含锁**）。2611269944 拆出来，让「等锁→忙」这条能测且不必动模型。"""
    if True:
        if backend == "flagreranker":
            # FlagReranker.compute_score 接受 list of [q, d] pairs
            pairs = [[query, d] for d in docs]
            scores = model.compute_score(pairs, normalize=True)
            # compute_score 单对返 float，多对返 list；统一 list
            if isinstance(scores, (int, float)):
                scores = [float(scores)]
            return [float(s) for s in scores]
        else:  # automodel
            import torch
            # 批量 tokenize（query + doc 拼接）；Task 562: 输入张量随模型上 MPS
            _dev = next(model.parameters()).device
            scores_out = []
            # Task 562: 分块批推理（chunk=8）+ 每次调用后 empty_cache——
            # 整批 20×512 token 的激活峰值会把 MPS allocator 缓存撑到 ~2.1G
            # 常驻 footprint（实测 3402MB 超预算）；分块压峰值，低频场景重分配
            # 开销可忽略（实测 8 docs 0.33s）。
            CHUNK = 8
            for i in range(0, len(docs), CHUNK):
                chunk = docs[i:i + CHUNK]
                encodings = tokenizer(
                    [query] * len(chunk), chunk,
                    padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt"
                )
                encodings = {k: v.to(_dev) for k, v in encodings.items()}
                with torch.no_grad():
                    logits = model(**encodings).logits.squeeze(-1)
                # Task 562: sigmoid 对齐 FlagReranker compute_score(normalize=True) 语义
                # （两 backend 分数口径一致，与历史融合分可比）
                probs = torch.sigmoid(logits.float())
                scores_out.extend(float(s) for s in probs.tolist())
            try:
                if _dev.type == "mps":
                    torch.mps.empty_cache()
            except Exception:
                pass
            return scores_out


def _rerank(query: str, documents: list, top_n: int = None) -> list:
    """精排：对 documents 按 (query, doc) 相关性分数排序。

    Returns: list[dict] 按分数降序，每项含 {index, score, document}。top_n 截取。
    """
    if not documents:
        return []
    scores = _compute_scores(query, documents)
    if len(scores) != len(documents):
        # 计算失败，返回原顺序（fail-safe）
        return [
            {"index": i, "score": 0.0, "document": documents[i]}
            for i in range(min(top_n or len(documents), len(documents)))
        ]
    indexed = [
        {"index": i, "score": scores[i], "document": documents[i]}
        for i in range(len(documents))
    ]
    indexed.sort(key=lambda x: x["score"], reverse=True)
    _STATE["scored"] += len(documents)
    if top_n is not None and top_n > 0:
        return indexed[:top_n]
    return indexed


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for _k, _v in (headers or {}).items():      # 2611269944：Retry-After 等
            self.send_header(_k, str(_v))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            uptime = time.time() - _STATE["started"]
            self._send(200, {
                "status": "ok" if _STATE["ready"] else "warming",
                "ready": _STATE["ready"],
                "model": _STATE["model"],
                "scored": _STATE["scored"],
                "uptime_sec": round(uptime, 1),
                "backend": _MODEL_CACHE.get("backend"),
                "lock_wait_ms": round(_LOCK_TIMEOUT * 1000, 1),   # 现读（测试可注入）
                "busy_rejects": _STATE.get("busy_rejects"),
                "keepwarm_sec": _STATE.get("keepwarm_sec"),
                "keepwarm_runs": _STATE.get("keepwarm_runs"),
                "keepwarm_last_ms": _STATE.get("keepwarm_last_ms"),
                "warmup_ms": _STATE.get("train_time_ms"),
                "max_doc_chars": MAX_DOC_CHARS,
                "max_len": MAX_LEN,
            })
            return
        if self.path == "/":
            self._send(200, {
                "service": "nexus-rerank",
                "version": "1.0.0",
                "port": DEFAULT_PORT,
                "model": RERANKER_MODEL_NAME,
                "endpoints": ["GET /health", "POST /rerank"],
            })
            return
        self._send(404, {"error": "Not Found"})

    def do_POST(self):
        if self.path != "/rerank":
            self._send(404, {"error": "Not Found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            payload = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send(400, {"error": f"无效 JSON: {e}"})
            return

        query = str(payload.get("query", "")).strip()
        documents = payload.get("documents", [])
        top_n = payload.get("top_n")
        if not isinstance(documents, list):
            self._send(400, {"error": "documents 必须是 list"})
            return
        if not query or not documents:
            self._send(400, {"error": "缺少 query 或 documents"})
            return
        if top_n is not None:
            try:
                top_n = int(top_n)
            except (TypeError, ValueError):
                top_n = None

        try:
            results = _rerank(query, documents, top_n=top_n)
        except BusyError as e:
            # 2611269944：忙 → 429 + Retry-After（客户端把「忙」当降级，不冷却、不重试）
            self._send(429, {"error": f"{e}", "busy": True, "retry_after": _RETRY_AFTER_SEC},
                       headers={"Retry-After": str(_RETRY_AFTER_SEC)})
            return
        except TimeoutError as e:
            # 老路径（其它地方抛的 TimeoutError）仍按 503 处理
            self._send(503, {"error": f"{e}（busy/超时，稍后重试）", "busy": True},
                       headers={"Retry-After": str(_RETRY_AFTER_SEC)})
            return
        except Exception as e:
            # 不泄漏 traceback 给客户端（BUG-12 模式），记 stderr
            print(f"[rerank_server] ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            self._send(500, {"error": f"rerank failed (见 stderr 日志)"})
            return

        self._send(200, {
            "results": results,
            "model": RERANKER_MODEL_NAME,
            "count": len(results),
        })

    def log_message(self, fmt, *args):
        # 简化日志（不刷屏），仅错误打到 stderr
        if args and "HTTP/1.1" in str(args[0]) and " 5" in str(args[0]) or " 4" in str(args[0]):
            sys.stderr.write(f"[rerank_server] {self.address_string()} - {fmt % args}\n")


def _warmup():
    """启动 warmup：触发模型加载 + 首次推理（避免真请求时延迟）。"""
    print(f"[rerank_server] warmup 开始...", flush=True)
    t0 = time.time()
    try:
        _compute_scores("warmup query", ["warmup document text"])
        # Task 562: 释放 warmup 峰值页（fp16 加载期间的临时缓冲，MALLOC 层归还未还页）
        import gc
        gc.collect()
        try:
            import torch
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass
        _STATE["ready"] = True
        _STATE["train_time_ms"] = round((time.time() - t0) * 1000, 1)
        print(f"[rerank_server] ✅ warmup 完成 ({time.time()-t0:.1f}s, "
              f"{_STATE['train_time_ms']:.0f}ms), "
              f"监听 http://{DEFAULT_HOST}:{DEFAULT_PORT}", flush=True)
    except Exception as e:
        print(f"[rerank_server] ❌ warmup 失败: {e}", file=sys.stderr, flush=True)
        _STATE["ready"] = False
        # 不立即退出，让 launchd KeepAlive 重启


def _keepwarm_loop():
    """2611269944：保温——每隔 `NEXUS_RERANK_KEEPWARM_SEC` 秒跑一次单篇推理。

    为什么需要：冷启动第一次慢是因为权重页被系统压掉/核函数首次编译（见 cold-start.txt 的测量），
    之后长时间不调用会再冷下去。保温成本是一次单篇推理（几十毫秒），换来「第一个真实请求不超时」。
    保温与真实请求共用同一把锁，所以它不会让真实请求多等太久：等不到就由真实请求按「忙」快速失败。
    """
    interval = _KEEPWARM_SEC
    if interval <= 0:
        print("[rerank_server] 保温关闭（NEXUS_RERANK_KEEPWARM_SEC=0）", flush=True)
        return
    while True:
        time.sleep(interval)
        t0 = time.time()
        try:
            _compute_scores("keepwarm", ["keepwarm document text"])
            _STATE["keepwarm_runs"] += 1
            _STATE["keepwarm_last_ms"] = round((time.time() - t0) * 1000, 1)
        except Exception as e:  # noqa: BLE001 — 保温失败不影响服务
            print(f"[rerank_server] 保温失败（不影响服务）: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)


def main():
    print(f"[rerank_server] 启动 (port={DEFAULT_PORT}, host={DEFAULT_HOST}, "
          f"busy_wait={_LOCK_TIMEOUT * 1000:.0f}ms, max_len={MAX_LEN}, "
          f"doc_chars={MAX_DOC_CHARS}, keepwarm={_KEEPWARM_SEC:.0f}s)", flush=True)
    # 异步 warmup（不阻塞 main 线程启动 HTTP 监听）
    threading.Thread(target=_warmup, daemon=True, name="rerank-warmup").start()
    threading.Thread(target=_keepwarm_loop, daemon=True, name="rerank-keepwarm").start()

    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[rerank_server] 收到 SIGINT，退出", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
