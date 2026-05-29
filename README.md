# Storage Cluster Monitor — Práctica 1 CNS

## Arquitectura

```
[Oruro  192.168.1.102]  ──┐
[La Paz 192.168.1.18  ]  ──┼── TCP:9000 ──▶  [Servidor CMN 10.251.68.102]
[Beni   192.168.1.34  ]  ──┘                      │
                                              HTTP:8080
                                                   │
                                            [Dashboard Web]
```

## Archivos

| Archivo          | Rol                                               |
|------------------|---------------------------------------------------|
| `cliente_ns.py`  | Corre en Oruro, La Paz, Beni — envía métricas    |
| `servidor_cmn.py`| Corre en 10.251.68.102 — recibe datos y sirve web  |
| `dashboard.html` | Interfaz web (debe estar junto al servidor)       |
| `requirements.txt`| Dependencias Python                              |

---

## Instalación

### En TODAS las máquinas (clientes y servidor)

```bash
pip install psutil
# o con pip3:
pip3 install psutil
```

---

## Uso

### 1. Primero: iniciar el servidor CMN (10.251.68.102)

```bash
python3 servidor_cmn.py
```

El servidor escuchará en:
- **Puerto 9000** → recibe métricas de los clientes NS
- **Puerto 8080** → dashboard web (abre en navegador: http://10.251.68.102:8080)

Opciones adicionales:
```bash
python3 servidor_cmn.py --puerto-socket 9000 --puerto-web 8080
```

---

### 2. Después: iniciar clientes NS en cada máquina

**En Oruro (192.168.1.102):**
```bash
python3 cliente_ns.py --servidor 10.251.68.102 --nombre "Oruro"
```

**En La Paz (192.168.1.18):**
```bash
python3 cliente_ns.py --servidor 10.251.68.102 --nombre "La Paz"
```

**En Beni (192.168.1.34):**
```bash
python3 cliente_ns.py --servidor 10.251.68.102 --nombre "Beni"
```

Opciones del cliente:
```bash
python3 cliente_ns.py --servidor IP --puerto 9000 --nombre NOMBRE --intervalo 10
```
- `--intervalo`: segundos entre cada envío (default: 10s)

---

### 3. Ver el dashboard

Abre en cualquier navegador de la red:
```
http://10.251.68.102:8080
```

El dashboard se actualiza automáticamente cada 5 segundos.

---

## Firewall (si hay problemas de conexión)

En el servidor CMN, abrir los puertos:
```bash
# Ubuntu/Debian
sudo ufw allow 9000/tcp
sudo ufw allow 8080/tcp

# CentOS/RHEL
sudo firewall-cmd --add-port=9000/tcp --permanent
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

---

## Protocolo de comunicación

Los clientes envían al servidor un JSON con este formato:

```json
{
  "nombre_nodo": "Oruro",
  "timestamp": "2025-01-01T12:00:00",
  "hostname": "pc-oruro",
  "os": "Linux 5.15.0",
  "discos": [
    {
      "dispositivo": "/dev/sda1",
      "mountpoint": "/",
      "tipo": "ext4",
      "capacidad_total_gb": 400.0,
      "espacio_usado_gb": 24.0,
      "espacio_libre_gb": 376.0,
      "porcentaje_uso": 6.0
    }
  ],
  "resumen": {
    "total_discos": 1,
    "capacidad_total_gb": 400.0,
    "espacio_usado_gb": 24.0,
    "espacio_libre_gb": 376.0,
    "porcentaje_uso": 6.0
  }
}
```

El servidor responde con `ACK` (3 bytes) para confirmar recepción.

---

## APIs del servidor

| Endpoint         | Descripción                            |
|------------------|----------------------------------------|
| `GET /`          | Dashboard web                          |
| `GET /api/estado`| JSON con todos los nodos y totales     |
| `GET /api/historial` | JSON con últimas 50 actualizaciones|
