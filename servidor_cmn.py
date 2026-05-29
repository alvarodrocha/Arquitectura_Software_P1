#!/usr/bin/env python3
"""
Servidor Centralized Monitoring Node (CMN)
- Escucha conexiones TCP de los clientes Node Storage en puerto 9000
- Consolida y almacena las métricas recibidas
- Sirve un dashboard web en puerto 8080

Uso:
    python3 servidor_cmn.py
    python3 servidor_cmn.py --puerto-socket 9000 --puerto-web 8080
"""

import socket
import json
import threading
import time
import argparse
import logging
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger("ServidorCMN")

# ─────────────────────────────────────────────
# Estado global compartido (protegido con lock)
# ─────────────────────────────────────────────
lock_nodos = threading.Lock()
nodos = {}          # { nombre_nodo: {...metricas_completas} }
historial = []      # Lista de últimos 200 eventos recibidos


def registrar_evento(nombre_nodo, resumen):
    """Agrega un evento al historial (máx 200 entradas)."""
    global historial
    historial.append({
        "timestamp":   datetime.now().isoformat(),
        "nodo":        nombre_nodo,
        "total_gb":    resumen.get("capacidad_total_gb", 0),
        "usado_gb":    resumen.get("espacio_usado_gb", 0),
        "libre_gb":    resumen.get("espacio_libre_gb", 0),
        "pct_uso":     resumen.get("porcentaje_uso", 0),
    })
    if len(historial) > 200:
        historial = historial[-200:]


def calcular_totales():
    """Calcula totales agregados de todo el cluster."""
    with lock_nodos:
        nodos_snap = list(nodos.values())

    if not nodos_snap:
        return {"total_gb": 0, "usado_gb": 0, "libre_gb": 0, "pct_uso": 0, "nodos_activos": 0}

    total_gb = sum(n["resumen"]["capacidad_total_gb"] for n in nodos_snap)
    usado_gb = sum(n["resumen"]["espacio_usado_gb"]   for n in nodos_snap)
    libre_gb = sum(n["resumen"]["espacio_libre_gb"]   for n in nodos_snap)
    pct_uso  = round((usado_gb / total_gb * 100) if total_gb > 0 else 0, 1)

    return {
        "total_gb":      round(total_gb, 2),
        "usado_gb":      round(usado_gb, 2),
        "libre_gb":      round(libre_gb, 2),
        "pct_uso":       pct_uso,
        "nodos_activos": len(nodos_snap),
    }


# ─────────────────────────────────────────────
# Servidor de sockets (recibe métricas)
# ─────────────────────────────────────────────

def manejar_cliente(conn, addr):
    """Procesa una conexión entrante de un cliente NS."""
    try:
        # Leer longitud del mensaje (4 bytes)
        raw_len = recibir_exacto(conn, 4)
        if not raw_len:
            return
        longitud = int.from_bytes(raw_len, byteorder="big")

        # Leer el payload JSON
        raw_data = recibir_exacto(conn, longitud)
        if not raw_data:
            return

        metricas = json.loads(raw_data.decode("utf-8"))
        nombre   = metricas.get("nombre_nodo", addr[0])

        # Agregar metadatos del servidor
        metricas["_ip_origen"]    = addr[0]
        metricas["_ultima_vista"] = datetime.now().isoformat()

        with lock_nodos:
            nodos[nombre] = metricas

        registrar_evento(nombre, metricas.get("resumen", {}))

        resumen = metricas.get("resumen", {})
        log.info(
            f"✓ [{nombre}] {addr[0]} | "
            f"Total: {resumen.get('capacidad_total_gb', '?')} GB | "
            f"Libre: {resumen.get('espacio_libre_gb', '?')} GB | "
            f"Uso: {resumen.get('porcentaje_uso', '?')}%"
        )

        conn.sendall(b"ACK")

    except json.JSONDecodeError:
        log.warning(f"JSON inválido recibido de {addr}")
    except Exception as e:
        log.error(f"Error manejando cliente {addr}: {e}")
    finally:
        conn.close()


def recibir_exacto(conn, n_bytes):
    """Lee exactamente n_bytes del socket."""
    buf = b""
    while len(buf) < n_bytes:
        chunk = conn.recv(n_bytes - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def servidor_sockets(host, puerto):
    """Bucle principal del servidor de sockets TCP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, puerto))
        srv.listen(20)
        log.info(f"[SOCKET] Escuchando en {host}:{puerto}")

        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(target=manejar_cliente, args=(conn, addr), daemon=True)
                t.start()
            except Exception as e:
                log.error(f"Error en accept(): {e}")


# ─────────────────────────────────────────────
# Servidor HTTP (dashboard web)
# ─────────────────────────────────────────────

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP por defecto

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_dashboard()
        elif self.path == "/api/estado":
            self._serve_api_estado()
        elif self.path == "/api/historial":
            self._serve_api_historial()
        else:
            self.send_error(404, "Ruta no encontrada")

    def _serve_dashboard(self):
        try:
            html = DASHBOARD_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        except FileNotFoundError:
            self.send_error(500, "dashboard.html no encontrado. Asegúrate de tenerlo en el mismo directorio.")

    def _serve_api_estado(self):
        with lock_nodos:
            nodos_snap = {k: v for k, v in nodos.items()}
        totales = calcular_totales()
        payload = json.dumps({
            "timestamp": datetime.now().isoformat(),
            "totales":   totales,
            "nodos":     nodos_snap,
        }, ensure_ascii=False, default=str)
        self._json_response(payload)

    def _serve_api_historial(self):
        payload = json.dumps({"historial": historial[-50:]}, ensure_ascii=False)
        self._json_response(payload)

    def _json_response(self, payload):
        data = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(data))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def servidor_web(host, puerto):
    """Inicia el servidor HTTP para el dashboard."""
    httpd = HTTPServer((host, puerto), DashboardHandler)
    log.info(f"[WEB] Dashboard disponible en http://{host}:{puerto}")
    httpd.serve_forever()


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Servidor CMN - Storage Cluster Monitor")
    parser.add_argument("--host",          default="0.0.0.0",
                        help="IP de escucha (default: 0.0.0.0)")
    parser.add_argument("--puerto-socket", type=int, default=9000,
                        help="Puerto para recibir métricas de clientes NS (default: 9000)")
    parser.add_argument("--puerto-web",    type=int, default=8080,
                        help="Puerto del dashboard web (default: 8080)")
    args = parser.parse_args()

    log.info("=" * 55)
    log.info("  Servidor CMN - Centralized Monitoring Node")
    log.info("=" * 55)

    # Hilo para recibir métricas por socket
    t_socket = threading.Thread(
        target=servidor_sockets,
        args=(args.host, args.puerto_socket),
        daemon=True
    )
    t_socket.start()

    # Hilo para el dashboard web
    t_web = threading.Thread(
        target=servidor_web,
        args=(args.host, args.puerto_web),
        daemon=True
    )
    t_web.start()

    log.info("Servidor CMN activo. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Servidor CMN detenido.")
        sys.exit(0)


if __name__ == "__main__":
    main()
