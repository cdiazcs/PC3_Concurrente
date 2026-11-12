#!/usr/bin/env python3
"""
Gateway HTTP/1.1 propio sobre sockets estándar (sin frameworks web ni WebSockets).
- Sirve el cliente web estático desde `clients/web/`.
- Recibe `POST /api/classify` con JSON (contrato v2 con imagenBase64 + vector 16x16).
- Valida tamaño, timeouts, JSON y Base64; traduce al protocolo TCP binario de 4 bytes
  big-endian (`IDENTIFY|...`) hacia CentralServer y retorna `RESULTADO_CLASIFICACION`.
"""
import argparse
import base64
import json
import math
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

MAX_HTTP_BODY = 2_000_000      # 2 MB máximo según PROTOCOLO_TCP_V1.md
MAX_HEADER_BYTES = 16_384      # 16 KB máximo para cabeceras HTTP
HTTP_READ_TIMEOUT = 10.0       # Timeout contra requests incompletas/lentas
TCP_BACKEND_TIMEOUT = float(os.getenv("WEB_BACKEND_TIMEOUT_SECONDS", "80"))     # Timeout de respuesta desde CentralServer

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "clients" / "web"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

ID_REGEX = re.compile(r"^[^\s|\x00-\x1f\x7f]{1,128}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_tcp_frame(host: str, port: int, message: str, timeout: float = TCP_BACKEND_TIMEOUT) -> str:
    """Envía un mensaje UTF-8 con prefijo de 4 bytes big-endian y lee la respuesta."""
    payload = message.encode("utf-8")
    if len(payload) > MAX_HTTP_BODY:
        raise ValueError("tcp_payload_too_large")

    with socket.create_connection((host, port), timeout=min(5.0, timeout)) as sock:
        deadline=time.monotonic()+timeout
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.sendall(struct.pack(">I", len(payload)) + payload)

        header = _recv_exact(sock, 4, deadline)
        if not header:
            raise ConnectionError("backend_eof_header")
        resp_len = struct.unpack(">I", header)[0]
        if resp_len <= 0 or resp_len > MAX_HTTP_BODY:
            raise ValueError("backend_invalid_length")

        body = _recv_exact(sock, resp_len, deadline)
        if not body:
            raise ConnectionError("backend_eof_body")
        return body.decode("utf-8")


def _recv_exact(sock: socket.socket, n: int, deadline=None) -> bytes:
    chunks = bytearray()
    while len(chunks) < n:
        if deadline is not None:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('backend_timeout')
            sock.settimeout(remaining)
        part = sock.recv(n - len(chunks))
        if not part:
            return b""
        chunks.extend(part)
    return bytes(chunks)


def build_http_response(status_code: int, status_text: str, content_type: str, body: bytes) -> bytes:
    headers = [
        f"HTTP/1.1 {status_code} {status_text}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Access-Control-Allow-Origin: *",
        "Access-Control-Allow-Methods: GET, POST, OPTIONS",
        "Access-Control-Allow-Headers: Content-Type",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii") + body


def json_response(status_code: int, status_text: str, data: dict) -> bytes:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return build_http_response(status_code, status_text, "application/json; charset=utf-8", raw)


def validate_and_extract_pixels(req_json: dict) -> tuple[str, str, str, str, list[float], str]:
    """
    Valida el JSON entrante (contrato v2) y devuelve:
    (id_solicitud, id_cliente, modelo_destino, modo, pixels_256, imagen_base64)
    """
    if not isinstance(req_json, dict):
        raise ValueError("json_root_must_be_object")

    id_solicitud = str(req_json.get("idSolicitud") or f"web-{uuid.uuid4()}").strip()
    id_cliente = str(req_json.get("idCliente") or "cliente-web-01").strip()
    modelo_destino = str(req_json.get("modeloDestino") or "A").strip().upper()
    modo = str(req_json.get("modo") or "SEQUENTIAL").strip().upper()

    if modelo_destino != 'A':
        raise ValueError('only_model_A_available')
    if os.getenv('CLIENT_PROTOCOL','V1') == 'V2' and (not isinstance(req_json.get('idCliente'),str) or not req_json['idCliente'].strip()):
        raise ValueError('client_identity_required')
    if not ID_REGEX.match(id_solicitud):
        raise ValueError("invalid_idSolicitud")
    if not ID_REGEX.match(id_cliente):
        raise ValueError("invalid_idCliente")
    if modo not in ("SEQUENTIAL", "DISTRIBUTED"):
        raise ValueError("invalid_modo_must_be_SEQUENTIAL_or_DISTRIBUTED")

    payload = req_json.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("missing_payload_object")

    imagen_b64 = str(payload.get("imagenBase64") or "").strip()
    if not imagen_b64:
        raise ValueError("missing_imagenBase64")

    # Validar Base64 real (soporta data URL o Base64 puro)
    b64_clean = imagen_b64.split(",", 1)[1] if "," in imagen_b64 else imagen_b64
    try:
        raw_img = base64.b64decode(b64_clean, validate=True)
        if len(raw_img) == 0 or len(raw_img) > 1_500_000:
            raise ValueError("invalid_image_byte_size")
    except Exception as exc:
        raise ValueError("invalid_base64_encoding") from exc

    pixels = payload.get("pixels")
    if not isinstance(pixels, list) or len(pixels) != 256:
        raise ValueError("pixels_must_be_array_of_256_floats")

    norm_pixels: list[float] = []
    for p in pixels:
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            raise ValueError("pixel_not_numeric")
        val = float(p)
        if not (0.0 <= val <= 1.0):
            raise ValueError("pixel_out_of_range_0_1")
        norm_pixels.append(round(val, 6))

    return id_solicitud, id_cliente, modelo_destino, modo, norm_pixels, b64_clean


def parse_tcp_identify_reply(reply: str, id_solicitud: str) -> dict:
    """Convierte `RESULT|id|1|3|p0,p1,p2` o `ERROR|id|code` a diccionario."""
    parts = reply.split("|")
    if len(parts) == 3 and parts[0] == "ERROR":
        if parts[1] != id_solicitud or not re.fullmatch(r'[A-Za-z0-9_:-]{1,128}',parts[2]):
            raise RuntimeError('invalid_backend_response_id')
        raise RuntimeError(f"backend_error:{parts[2]}")

    if len(parts) != 5 or parts[0] != "RESULT" or parts[1] != id_solicitud or parts[2] != "1" or parts[3] != "3":
        raise RuntimeError("invalid_backend_response_format")

    try:probs = [float(x) for x in parts[4].split(",")]
    except ValueError:raise RuntimeError('invalid_probability_vector') from None
    if len(probs) != 3 or any(not math.isfinite(p) or not 0<=p<=1 for p in probs) or abs(sum(probs)-1)>1e-8:
        raise RuntimeError("invalid_probability_vector")

    labels = ["circulo", "cruz", "triangulo"]
    best_idx = max(range(3), key=lambda i: probs[i])
    return {
        "etiqueta": labels[best_idx],
        "probabilidades": {
            "circulo": round(probs[0], 6),
            "cruz": round(probs[1], 6),
            "triangulo": round(probs[2], 6),
        },
    }


class HttpGatewayServer:
    def __init__(self, bind_host: str, bind_port: int, backend_host: str, backend_port: int):
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.backend_host = backend_host
        self.backend_port = backend_port
        self._stop_event = threading.Event()
        self._slots=threading.BoundedSemaphore(int(os.getenv("WEB_MAX_CLIENTS","128")))
        self._sock: socket.socket | None = None

    def serve_forever(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.bind_host, self.bind_port))
        self._sock.listen(128)
        self._sock.settimeout(1.0)
        print(
            f"[HTTP-GATEWAY] Escuchando en http://{self.bind_host}:{self.bind_port} "
            f"-> Backend TCP {self.backend_host}:{self.backend_port}"
        )
        while not self._stop_event.is_set():
            try:
                conn, addr = self._sock.accept()
                if not self._slots.acquire(blocking=False):
                    conn.close();continue
                t = threading.Thread(target=self._serve_client, args=(conn, addr), daemon=True)
                try:t.start()
                except Exception:
                    conn.close();self._slots.release();raise
            except socket.timeout:
                continue
            except OSError:
                break

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _serve_client(self,conn,addr):
        try:self._handle_client(conn,addr)
        finally:self._slots.release()

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        with conn:
            conn.settimeout(HTTP_READ_TIMEOUT)
            try:
                raw_req = self._read_http_request(conn)
                if raw_req is None:
                    return
                method, target, headers, body = raw_req
                response_bytes = self._route(method, target, headers, body)
                conn.sendall(response_bytes)
            except socket.timeout:
                try:
                    conn.sendall(json_response(408, "Request Timeout", {"error": "http_read_timeout"}))
                except OSError:
                    pass
            except ValueError as ve:
                try:
                    conn.sendall(json_response(400, "Bad Request", {"error": str(ve)}))
                except OSError:
                    pass
            except Exception as exc:
                try:
                    conn.sendall(json_response(500, "Internal Server Error", {"error": str(exc)}))
                except OSError:
                    pass

    def _read_http_request(self, conn: socket.socket) -> tuple[str, str, dict[str, str], bytes] | None:
        buffer = bytearray()
        header_end = -1
        deadline=time.monotonic()+HTTP_READ_TIMEOUT
        while header_end == -1:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('http_read_timeout')
            conn.settimeout(remaining)
            chunk = conn.recv(4096)
            if not chunk:
                if len(buffer) == 0:
                    return None
                raise ValueError("incomplete_http_headers")
            buffer.extend(chunk)
            if len(buffer) > MAX_HEADER_BYTES:
                raise ValueError("headers_too_large")
            header_end = buffer.find(b"\r\n\r\n")

        head_bytes = bytes(buffer[:header_end])
        body_so_far = bytearray(buffer[header_end + 4 :])

        lines = head_bytes.decode("iso-8859-1").split("\r\n")
        request_line = lines[0].split(" ")
        if len(request_line) != 3:
            raise ValueError("malformed_request_line")
        method, target, _version = request_line[0].upper(), request_line[1], request_line[2]

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                key=k.strip().lower()
                if key in headers:raise ValueError('duplicate_http_header')
                headers[key] = v.strip()

        if 'transfer-encoding' in headers:raise ValueError('unsupported_transfer_encoding')
        content_length = 0
        if "content-length" in headers:
            if not headers["content-length"].isdigit():
                raise ValueError("invalid_content_length")
            content_length = int(headers["content-length"])
            if content_length > MAX_HTTP_BODY:
                raise ValueError("payload_too_large")

        while len(body_so_far) < content_length:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('http_read_timeout')
            conn.settimeout(remaining)
            chunk = conn.recv(min(8192, content_length - len(body_so_far)))
            if not chunk:
                raise ValueError("incomplete_http_body")
            body_so_far.extend(chunk)

        return method, target, headers, bytes(body_so_far[:content_length])

    def _route(self, method: str, target: str, headers: dict[str, str], body: bytes) -> bytes:
        path = unquote(target.split("?", 1)[0])

        if method == "OPTIONS":
            return build_http_response(204, "No Content", "text/plain", b"")

        if method == "GET" and path == "/api/health":
            return json_response(
                200,
                "OK",
                {
                    "status": "ok",
                    "gateway": "python-raw-socket",
                    "backend": f"{self.backend_host}:{self.backend_port}",
                    "timestamp": utc_now_iso(),
                },
            )

        if method == "POST" and path == "/api/classify":
            return self._handle_classify(body)

        if method == "GET":
            return self._serve_static(path)

        return json_response(405, "Method Not Allowed", {"error": "method_not_allowed"})

    def _serve_static(self, path: str) -> bytes:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        candidate = (WEB_DIR / rel).resolve()
        # Evitar path traversal fuera de clients/web
        if not str(candidate).startswith(str(WEB_DIR.resolve())) or not candidate.is_file():
            return json_response(404, "Not Found", {"error": "file_not_found"})

        mime = MIME_TYPES.get(candidate.suffix.lower(), "application/octet-stream")
        return build_http_response(200, "OK", mime, candidate.read_bytes())

    def _handle_classify(self, body: bytes) -> bytes:
        if not body:
            raise ValueError("empty_body")
        try:
            req_json = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid_json") from exc

        id_solicitud, id_cliente, modelo_destino, modo, pixels, image_base64 = validate_and_extract_pixels(req_json)

        # Permitir override dinámico de backend desde UI si se envía en el JSON
        b_host = str(req_json.get("backendHost") or self.backend_host).strip()
        b_port = int(req_json.get("backendPort") or self.backend_port)

        pixels_csv = ",".join(f"{p:.6f}".rstrip("0").rstrip(".") or "0" for p in pixels)
        if os.environ.get('CLIENT_PROTOCOL', 'V1') == 'V2':
            raw = base64.b64decode(image_base64, validate=True)
            mime = 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else ('image/jpeg' if raw.startswith(b'\xff\xd8') else 'image/x-portable-graymap')
            tcp_msg = f"IDENTIFY2|{id_solicitud}|{id_cliente}|{modo}|{mime}|{image_base64}"
        else:
            tcp_msg = f"IDENTIFY|{id_solicitud}|{pixels_csv}|{modo}"

        t0 = time.perf_counter()
        try:
            tcp_reply = send_tcp_frame(b_host, b_port, tcp_msg)
        except Exception as exc:
            return json_response(
                502,
                "Bad Gateway",
                {
                    "schemaVersion": 1,
                    "tipo": "ERROR_CLASIFICACION",
                    "idSolicitud": id_solicitud,
                    "idCliente": id_cliente,
                    "error": f"backend_unreachable:{exc}",
                },
            )
        duracion_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        try:
            pred = parse_tcp_identify_reply(tcp_reply, id_solicitud)
        except RuntimeError as re_err:
            return json_response(
                422,
                "Unprocessable Entity",
                {
                    "schemaVersion": 1,
                    "tipo": "ERROR_CLASIFICACION",
                    "idSolicitud": id_solicitud,
                    "idCliente": id_cliente,
                    "error": str(re_err),
                },
            )

        # Respuesta alineada con contracts/examples/resultado_modeloA.json
        result_payload = {
            "schemaVersion": 1,
            "tipo": "RESULTADO_CLASIFICACION",
            "idSolicitud": id_solicitud,
            "idCliente": id_cliente,
            "modeloDestino": modelo_destino,
            "timestamp": utc_now_iso(),
            "payload": {
                "etiqueta": pred["etiqueta"],
                "probabilidades": pred["probabilidades"],
                "duracionMs": duracion_ms,
                "modo": modo,
            },
        }
        return json_response(200, "OK", result_payload)


def run_self_tests() -> None:
    """Prueba requests incompletas y concurrentes exigidas en web-server/README.md."""
    import concurrent.futures

    # Levantar mock TCP del backend y gateway en puertos efímeros
    mock_backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    mock_backend.bind(("127.0.0.1", 0))
    mock_backend.listen(32)
    b_port = mock_backend.getsockname()[1]

    def mock_backend_loop():
        while True:
            try:
                c, _ = mock_backend.accept()
            except OSError:
                break
            with c:
                hdr = _recv_exact(c, 4)
                if not hdr:
                    continue
                ln = struct.unpack(">I", hdr)[0]
                msg = _recv_exact(c, ln).decode("utf-8")
                req_id = msg.split("|")[1]
                out = f"RESULT|{req_id}|1|3|0.91,0.05,0.04".encode("utf-8")
                c.sendall(struct.pack(">I", len(out)) + out)

    threading.Thread(target=mock_backend_loop, daemon=True).start()

    gw = HttpGatewayServer("127.0.0.1", 0, "127.0.0.1", b_port)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    time.sleep(0.2)
    gw_port = gw._sock.getsockname()[1]

    # 1. Prueba de request incompleta (cierra socket a mitad de body)
    with socket.create_connection(("127.0.0.1", gw_port), timeout=3) as s:
        s.sendall(b"POST /api/classify HTTP/1.1\r\nHost: localhost\r\nContent-Length: 500\r\n\r\n{\"parcial\":")
        s.shutdown(socket.SHUT_WR)
        resp = s.recv(4096).decode("utf-8", errors="ignore")
        assert "400 Bad Request" in resp, f"Esperaba 400 para request incompleta, obtuvo: {resp}"

    # 2. Prueba concurrente (20 peticiones simultáneas)
    dummy_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    pixels = [0.0] * 256

    def fire(idx: int) -> str:
        body = json.dumps({
            "schemaVersion": 1,
            "idSolicitud": f"conc-{idx}",
            "idCliente": "cliente-web-01",
            "modeloDestino": "A",
            "modo": "SEQUENTIAL",
            "payload": {"mimeType": "image/png", "imagenBase64": dummy_b64, "pixels": pixels},
        }).encode("utf-8")
        req = (
            f"POST /api/classify HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
        ).encode("ascii") + body
        with socket.create_connection(("127.0.0.1", gw_port), timeout=5) as s:
            s.sendall(req)
            raw = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
        text = raw.decode("utf-8")
        assert "200 OK" in text and f"conc-{idx}" in text
        return text

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(fire, range(20)))

    gw.shutdown()
    mock_backend.close()
    print(f"[OK] Self-test superado: request incompleta rechazada (400) + {len(results)} peticiones concurrentes exitosas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gateway HTTP propio para Cliente Web PC3")
    parser.add_argument("--host", default=os.getenv("WEB_GW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_GW_PORT", "8080")))
    parser.add_argument("--backend-host", default=os.getenv("BACKEND_HOST", "127.0.0.1"))
    parser.add_argument("--backend-port", type=int, default=int(os.getenv("BACKEND_PORT", "9000")))
    parser.add_argument("--self-test", action="store_true", help="Ejecuta pruebas de concurrencia y requests incompletas")
    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        sys.exit(0)

    server = HttpGatewayServer(args.host, args.port, args.backend_host, args.backend_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HTTP-GATEWAY] Deteniendo servidor...")
        server.shutdown()