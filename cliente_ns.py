#!/usr/bin/env python3
"""
Cliente Node Storage (NS)
Recolecta información del disco duro y la envía al Servidor CMN via sockets TCP.

Uso:
    python3 cliente_ns.py --servidor 10.251.68.102 --puerto 9000 --nombre "Oruro"
    python3 cliente_ns.py --servidor 10.251.68.102 --puerto 9000 --nombre "La Paz"
    python3 cliente_ns.py --servidor 10.251.68.102 --puerto 9000 --nombre "Beni"
"""

import socket
import json
import time
import psutil
import platform
import argparse
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger("ClienteNS")


def obtener_info_discos():
    """Recolecta información de todos los discos/particiones del sistema."""
    discos = []
    particiones = psutil.disk_partitions(all=False)

    for particion in particiones:
        try:
            uso = psutil.disk_usage(particion.mountpoint)
            discos.append({
                "dispositivo":   particion.device,
                "mountpoint":    particion.mountpoint,
                "tipo":          particion.fstype,
                "capacidad_total_gb": round(uso.total / (1024 ** 3), 2),
                "espacio_usado_gb":   round(uso.used  / (1024 ** 3), 2),
                "espacio_libre_gb":   round(uso.free  / (1024 ** 3), 2),
                "porcentaje_uso":     uso.percent,
            })
        except PermissionError:
            continue  # Saltar particiones sin permiso de lectura

    return discos


def obtener_metricas():
    """Construye el payload completo de métricas del nodo."""
    discos = obtener_info_discos()

    # Totales agregados del nodo
    total_gb  = sum(d["capacidad_total_gb"] for d in discos)
    usado_gb  = sum(d["espacio_usado_gb"]   for d in discos)
    libre_gb  = sum(d["espacio_libre_gb"]   for d in discos)
    pct_uso   = round((usado_gb / total_gb * 100) if total_gb > 0 else 0, 1)

    return {
        "timestamp":     datetime.now().isoformat(),
        "hostname":      platform.node(),
        "os":            f"{platform.system()} {platform.release()}",
        "discos":        discos,
        "resumen": {
            "total_discos":        len(discos),
            "capacidad_total_gb":  round(total_gb, 2),
            "espacio_usado_gb":    round(usado_gb, 2),
            "espacio_libre_gb":    round(libre_gb, 2),
            "porcentaje_uso":      pct_uso,
        }
    }


def enviar_metricas(servidor_ip, puerto, nombre_nodo, intervalo_seg):
    """Bucle principal: recolecta y envía métricas periódicamente."""
    log.info(f"Nodo: '{nombre_nodo}' | Servidor CMN: {servidor_ip}:{puerto} | Intervalo: {intervalo_seg}s")

    while True:
        try:
            metricas = obtener_metricas()
            metricas["nombre_nodo"] = nombre_nodo  # Identificador legible

            payload = json.dumps(metricas, ensure_ascii=False)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((servidor_ip, puerto))

                # Protocolo: enviar longitud (4 bytes) + datos
                datos = payload.encode("utf-8")
                longitud = len(datos).to_bytes(4, byteorder="big")
                s.sendall(longitud + datos)

                # Esperar ACK del servidor
                ack = s.recv(3)
                if ack == b"ACK":
                    resumen = metricas["resumen"]
                    log.info(
                        f"✓ Enviado | Total: {resumen['capacidad_total_gb']} GB | "
                        f"Usado: {resumen['espacio_usado_gb']} GB | "
                        f"Libre: {resumen['espacio_libre_gb']} GB ({resumen['porcentaje_uso']}%)"
                    )
                else:
                    log.warning(f"Respuesta inesperada del servidor: {ack}")

        except ConnectionRefusedError:
            log.error(f"No se pudo conectar a {servidor_ip}:{puerto}. ¿Está el servidor CMN activo?")
        except socket.timeout:
            log.error("Tiempo de espera agotado al conectar con el servidor.")
        except Exception as e:
            log.error(f"Error inesperado: {e}")

        log.info(f"Próximo envío en {intervalo_seg} segundos...")
        time.sleep(intervalo_seg)


def main():
    parser = argparse.ArgumentParser(
        description="Cliente Node Storage - envía métricas de disco al servidor CMN"
    )
    parser.add_argument("--servidor", default="10.251.68.102",
                        help="IP del servidor CMN (default: 10.251.68.102)")
    parser.add_argument("--puerto",   type=int, default=9000,
                        help="Puerto del servidor CMN (default: 9000)")
    parser.add_argument("--nombre",   default=platform.node(),
                        help="Nombre identificador del nodo (ej: Oruro, La Paz, Beni)")
    parser.add_argument("--intervalo",type=int, default=10,
                        help="Segundos entre cada envío de métricas (default: 10)")
    args = parser.parse_args()

    try:
        enviar_metricas(args.servidor, args.puerto, args.nombre, args.intervalo)
    except KeyboardInterrupt:
        log.info("Cliente detenido por el usuario.")
        sys.exit(0)


if __name__ == "__main__":
    main()
