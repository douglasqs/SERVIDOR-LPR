import datetime
import ipaddress
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
import socket
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPDigestAuth
from flask import Flask, jsonify, make_response, render_template, request
from werkzeug.exceptions import HTTPException

try:
    import webview
except Exception:
    webview = None


def _first_existing(candidates, fallback):
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return fallback


if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    bundle_dir = getattr(sys, "_MEIPASS", exe_dir)
    template_folder = _first_existing(
        [
            os.path.join(bundle_dir, "templates"),
            os.path.join(exe_dir, "templates"),
        ],
        os.path.join(bundle_dir, "templates"),
    )
    static_folder = _first_existing(
        [
            os.path.join(bundle_dir, "static"),
            os.path.join(exe_dir, "static"),
        ],
        os.path.join(bundle_dir, "static"),
    )
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    BASE_DIR = exe_dir
else:
    app = Flask(__name__)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


ERROR_LOG = os.path.join(BASE_DIR, "error.log")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
APP_NAME = "multimo - Tester Hikvision"

DEFAULT_CONFIG = {
    "server_host": "0.0.0.0",
    "port": 8080,
    "ack_enabled": True,
    "device_user": "admin",
    "device_password": "password",
    "remote_verify_enabled": False,
}

server_config = {}
events_log = []
event_id_counter = 0
access_event_counter = 0
anpr_event_counter = 0

LOG_DIR = os.path.join(BASE_DIR, "logs")
IMAGES_DIR = os.path.join(BASE_DIR, "captured_images")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    c_handler = logging.StreamHandler()
    c_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(c_handler)

log_file = os.path.join(LOG_DIR, "hikvision_server.log")
if not any(
    isinstance(h, TimedRotatingFileHandler) and getattr(h, "baseFilename", None) == log_file
    for h in logger.handlers
):
    f_handler = TimedRotatingFileHandler(log_file, when="h", interval=1, backupCount=168, encoding="utf-8")
    f_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    f_handler.suffix = "%Y-%m-%d_%Hh.log"
    logger.addHandler(f_handler)


def load_config():
    global server_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            server_config = DEFAULT_CONFIG.copy()
            server_config.update(loaded)
            return
        except Exception as e:
            print(f"[!] Erro ao carregar config: {e}")

    server_config = DEFAULT_CONFIG.copy()
    save_config()


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(server_config, f, indent=4, ensure_ascii=False)
        print("[*] Configuracao salva.")
    except Exception as e:
        print(f"[!] Erro ao salvar config: {e}")


def is_valid_ipv4(address):
    try:
        return isinstance(ipaddress.ip_address(address), ipaddress.IPv4Address)
    except ValueError:
        return False


def _append_network_interface(interfaces, seen, address, name):
    address = str(address or "").strip()
    if not is_valid_ipv4(address) or address in seen:
        return

    seen.add(address)
    name = str(name or "").strip()
    label = f"{name} - {address}" if name and name != address else address
    interfaces.append({"address": address, "name": name or address, "label": label})


def hidden_subprocess_kwargs():
    if os.name != "nt":
        return {}

    kwargs = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except AttributeError:
        pass

    return kwargs


def get_network_interfaces(include_configured=True):
    interfaces = []
    seen = set()

    _append_network_interface(interfaces, seen, "0.0.0.0", "Todas as interfaces")
    _append_network_interface(interfaces, seen, "127.0.0.1", "Somente este computador")

    if os.name == "nt":
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=3,
                **hidden_subprocess_kwargs(),
            )
            adapter_name = ""
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if not line[:1].isspace() and stripped.endswith(":"):
                    adapter_name = stripped.rstrip(":")
                    continue
                if "IPv4" in stripped:
                    match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", stripped)
                    if match:
                        _append_network_interface(interfaces, seen, match.group(1), adapter_name)
        except Exception as e:
            logging.debug("Falha ao listar interfaces via ipconfig: %s", e)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            _append_network_interface(interfaces, seen, info[4][0], "Host")
    except OSError as e:
        logging.debug("Falha ao listar interfaces via socket: %s", e)

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(1)
        probe.connect(("8.8.8.8", 80))
        _append_network_interface(interfaces, seen, probe.getsockname()[0], "Rota padrão")
        probe.close()
    except OSError as e:
        logging.debug("Falha ao detectar rota padrão: %s", e)

    configured_host = str(server_config.get("server_host", DEFAULT_CONFIG["server_host"])).strip()
    if include_configured and configured_host and configured_host not in seen and is_valid_ipv4(configured_host):
        _append_network_interface(interfaces, seen, configured_host, "Configurado")

    return interfaces


def get_effective_server_host():
    configured_host = str(server_config.get("server_host", DEFAULT_CONFIG["server_host"])).strip()
    if not is_valid_ipv4(configured_host):
        return DEFAULT_CONFIG["server_host"]
    if configured_host in ("0.0.0.0", "127.0.0.1"):
        return configured_host

    available_hosts = {item["address"] for item in get_network_interfaces(include_configured=False)}
    if configured_host not in available_hosts:
        logging.warning(
            "[!] IP configurado %s nao encontrado nesta maquina. Usando 0.0.0.0.",
            configured_host,
        )
        return DEFAULT_CONFIG["server_host"]

    return configured_host


def settings_response():
    payload = server_config.copy()
    payload["server_host"] = str(payload.get("server_host") or DEFAULT_CONFIG["server_host"])
    payload["effective_server_host"] = get_effective_server_host()
    payload["network_interfaces"] = get_network_interfaces()
    return payload


load_config()


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e

    import traceback

    tb = traceback.format_exc()
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] UNHANDLED EXCEPTION:\n{tb}\n")
            if getattr(sys, "frozen", False):
                f.write(f"  template_folder = {app.template_folder}\n")
                f.write(f"  _MEIPASS = {getattr(sys, '_MEIPASS', 'N/A')}\n")
                f.write(f"  BASE_DIR = {BASE_DIR}\n")
    except Exception:
        pass

    return make_response(f"<pre>Internal Server Error\n\n{tb}</pre>", 500)


def log_event(path, method, client_ip, data, status_code, log_to_file=False, event_source="facial"):
    global event_id_counter
    event_id_counter += 1

    entry = {
        "id": event_id_counter,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "path": path,
        "method": method,
        "client_ip": client_ip,
        "data": data,
        "status": status_code,
        "event_source": event_source,
    }

    events_log.append(entry)
    if len(events_log) > 100:
        events_log.pop(0)

    msg = f"# RECV {method} {path} from {client_ip} | Status: {status_code}"
    if log_to_file:
        logging.info(f"{msg} | Data: {json.dumps(entry['data'], ensure_ascii=False)}")
    else:
        print(f"[{entry['timestamp']}] {msg}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        updated = False

        if "ack_enabled" in data:
            server_config["ack_enabled"] = bool(data["ack_enabled"])
            updated = True

        if "server_host" in data:
            host = str(data["server_host"]).strip()
            if is_valid_ipv4(host):
                server_config["server_host"] = host
                updated = True

        if "port" in data:
            try:
                p = int(data["port"])
                if 1024 <= p <= 65535:
                    server_config["port"] = p
                    updated = True
            except ValueError:
                pass

        if "device_user" in data:
            server_config["device_user"] = str(data["device_user"])
            updated = True

        if "device_password" in data:
            server_config["device_password"] = str(data["device_password"])
            updated = True

        if "remote_verify_enabled" in data:
            server_config["remote_verify_enabled"] = bool(data["remote_verify_enabled"])
            updated = True

        if updated:
            save_config()

    return jsonify(settings_response())


@app.route("/api/meta", methods=["GET"])
def get_meta():
    return jsonify(
        {
            "access_event_count": access_event_counter,
            "anpr_event_count": anpr_event_counter,
        }
    )


@app.route("/api/events", methods=["GET", "DELETE"])
def get_events():
    global access_event_counter, anpr_event_counter

    if request.method == "DELETE":
        events_log.clear()
        access_event_counter = 0
        anpr_event_counter = 0
        return jsonify(
            {
                "success": True,
                "last_event_id": event_id_counter,
                "access_event_count": access_event_counter,
                "anpr_event_count": anpr_event_counter,
            }
        )

    return jsonify(events_log)


@app.route("/images/<path:filename>")
def serve_image(filename):
    from flask import send_from_directory

    return send_from_directory(IMAGES_DIR, filename)


@app.route("/api/remote_verify", methods=["POST"])
def remote_verify():
    data = request.get_json(silent=True) or {}
    serial_no = data.get("serialNo")
    if "ipAddress" not in data or serial_no is None:
        return jsonify({"success": False, "error": "Faltam parametros ipAddress e serialNo"}), 400

    success, msg, code = do_remote_verify(data["ipAddress"], serial_no)
    if success:
        return jsonify({"success": True, "message": msg, "status_code": code}), code
    return jsonify({"success": False, "error": msg}), code


def do_remote_verify(ip, serial_no):
    """Executes Hikvision remoteCheck API call."""
    user = server_config.get("device_user", "admin")
    password = server_config.get("device_password", "password")
    url = f"http://{ip}/ISAPI/AccessControl/remoteCheck?format=json"
    serial_no_value = int(serial_no) if isinstance(serial_no, str) and serial_no.isdigit() else serial_no
    payload_str = json.dumps({"RemoteCheck": {"serialNo": serial_no_value, "checkResult": "success"}})
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.put(
            url,
            data=payload_str,
            headers=headers,
            auth=HTTPDigestAuth(user, password),
            timeout=3,
        )
        response.raise_for_status()
        logger.info(f"[*] Remote Verify (Check) bem-sucedido para {ip} (Serial: {serial_no})")
        return True, "Acesso liberado (Check)", response.status_code
    except Exception as e:
        logger.debug(f"RemoteVerify falhou para {ip}: {e}")
        return False, str(e), 500


def should_auto_remote_verify(ace):
    rc_field = ace.get("remoteCheck")
    is_rc_true = rc_field is True or str(rc_field).lower() == "true"
    major_event_type = str(ace.get("majorEventType", ""))
    sub_event_type = str(ace.get("subEventType", ""))
    is_successful_access_event = major_event_type == "5" and sub_event_type in ("75", "76")
    return is_rc_true or is_successful_access_event


def _strip_namespace(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _xml_value(node):
    children = list(node)
    if children:
        return {_strip_namespace(child.tag): _xml_value(child) for child in children}
    return (node.text or "").strip()


def _parse_xml_event_to_dict(xml_body):
    """Parse a raw Hikvision XML EventNotificationAlert body into a plain dict."""
    try:
        if isinstance(xml_body, bytes):
            xml_body = xml_body.decode("utf-8", errors="ignore")

        xml_clean = re.sub(r'\s+xmlns[^=]*="[^"]*"', "", xml_body.strip())
        root = ET.fromstring(xml_clean)

        def _t(tag, default=""):
            el = root.find(f".//{tag}")
            return el.text.strip() if el is not None and el.text else default

        result = {
            "ipAddress": _t("ipAddress"),
            "macAddress": _t("macAddress"),
            "channelID": _t("channelID"),
            "dateTime": _t("dateTime"),
            "activePostCount": _t("activePostCount"),
            "eventType": _t("eventType"),
            "eventState": _t("eventState"),
            "eventDescription": _t("eventDescription"),
        }

        ace_node = root.find(".//AccessControllerEvent")
        if ace_node is not None:
            result["AccessControllerEvent"] = {
                _strip_namespace(child.tag): _xml_value(child)
                for child in ace_node
                if child.text or list(child)
            }

        return result
    except Exception:
        return None


def _parse_mixed_target_detection(json_str):
    """
    Parse Hikvision mixedTargetDetection JSON payload from ANPR cameras.
    Returns normalized data for the dashboard, or None when no plate is found.
    """
    try:
        d = json.loads(json_str)
    except Exception:
        return None

    results = d.get("CaptureResult", [])
    if not results:
        return None

    for capture in results:
        vehicle = capture.get("Vehicle", {})
        props = {
            p["description"]: p["value"]
            for p in vehicle.get("Property", [])
            if "description" in p and "value" in p
        }
        plate = props.get("plateNo", "").strip()
        if not plate:
            continue

        image_ids = {
            "vehicleImage": vehicle.get("pId1"),
            "plateImage": vehicle.get("pId2"),
            "backgroundImage": vehicle.get("pId3"),
        }
        return {
            "eventType": "mixedTargetDetection",
            "dateTime": d.get("dateTime", ""),
            "ipAddress": d.get("ipAddress", ""),
            "macAddress": d.get("macAddress", ""),
            "channelID": str(d.get("channelID", "")),
            "channelName": d.get("channelName", ""),
            "plateNumber": plate,
            "plateConfidence": props.get("confidence", ""),
            "vehicleType": props.get("vehicleType", ""),
            "vehicleColor": props.get("vehicleColor", ""),
            "vehicleBrand": props.get("vehicleLogoString", ""),
            "vehicleDirection": "",
            "_image_ids": image_ids,
        }

    return None


_anpr_dedup = {}
_anpr_dedup_lock = threading.Lock()
ANPR_DEDUP_SECONDS = 5


def _save_uploaded_file(file_storage, prefix):
    if not file_storage:
        return None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{ts}.jpg"
    file_storage.save(os.path.join(IMAGES_DIR, filename))
    return f"/images/{filename}"


def _first_event_json_from_form():
    event_log = request.form.get("event_log")
    if event_log:
        return event_log

    for value in request.form.values():
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text.startswith("{") and ("eventType" in text or "AccessControllerEvent" in text):
            return text
    return None


def _first_uploaded_image(preferred_fields):
    for field in preferred_fields:
        if field in request.files:
            file = request.files[field]
            if file and file.filename:
                return file

    for file in request.files.values():
        if file and file.filename:
            return file
    return None


@app.route("/", methods=["POST"])
def receive_hikvision_event():
    """
    Receives Hikvision event notifications:
      1. multipart mixedTargetDetection JSON field from ANPR cameras
      2. multipart event_log JSON field from facial/access terminals
      3. XML raw body fallback
      4. JSON raw body fallback
    """
    global access_event_counter, anpr_event_counter

    ack_enabled = server_config.get("ack_enabled", True)
    client_ip = request.remote_addr
    data = {}
    content_type = (request.content_type or "").lower()
    raw_body = request.data

    try:
        mtd_raw = request.form.get("mixedTargetDetection")
        if mtd_raw:
            parsed = _parse_mixed_target_detection(mtd_raw)
            if not parsed:
                return "", 200 if ack_enabled else 500

            ip_cam = parsed.get("ipAddress") or client_ip
            plate_key = (ip_cam, parsed["plateNumber"])
            now = datetime.datetime.now().timestamp()
            with _anpr_dedup_lock:
                stale_keys = [key for key, ts in _anpr_dedup.items() if now - ts >= ANPR_DEDUP_SECONDS]
                for key in stale_keys:
                    _anpr_dedup.pop(key, None)

                last_seen = _anpr_dedup.get(plate_key, 0)
                if now - last_seen < ANPR_DEDUP_SECONDS:
                    return "", 200
                _anpr_dedup[plate_key] = now

            image_url = None
            for img_name, content_id in (parsed.pop("_image_ids", {}) or {}).items():
                if img_name != "vehicleImage" or not content_id:
                    continue
                image_url = _save_uploaded_file(request.files.get(content_id), "anpr")
                if image_url:
                    break

            data = parsed
            anpr_event_counter += 1
            status_code = 200 if ack_enabled else 500
            log_event("/", "POST", client_ip, data, status_code, log_to_file=True, event_source="anpr")
            if image_url and events_log:
                events_log[-1]["image_url"] = image_url

            logger.info(
                "[ANPR] Placa (push): '%s' | %s %s | %s",
                data["plateNumber"],
                data.get("vehicleBrand", ""),
                data.get("vehicleColor", ""),
                ip_cam,
            )
            return "", status_code

        event_log_raw = _first_event_json_from_form()
        if not event_log_raw and not raw_body and not request.form:
            return "", 200

        if event_log_raw:
            data = json.loads(event_log_raw)
        elif "xml" in content_type or (raw_body and raw_body.lstrip()[:5] in (b"<?xml", b"<Even")):
            parsed_xml = _parse_xml_event_to_dict(raw_body)
            data = parsed_xml or {"raw": raw_body.decode("utf-8", errors="ignore")[:500]}
        else:
            data = request.get_json(force=True) or {}
    except json.JSONDecodeError as e:
        data = {"parse_error": str(e)}
    except Exception as e:
        data = {"error": str(e)}

    event_type = data.get("eventType", "")
    if event_type == "heartBeat":
        return "", 200

    if event_type == "AccessControllerEvent":
        access_event_counter += 1
        ace = data.get("AccessControllerEvent", {})
        remote_verify_enabled = server_config.get("remote_verify_enabled", False)
        is_verify_request = should_auto_remote_verify(ace)

        if remote_verify_enabled and is_verify_request:
            ips_to_try = []
            if data.get("ipAddress"):
                ips_to_try.append(data.get("ipAddress"))
            if client_ip and client_ip not in ips_to_try:
                ips_to_try.append(client_ip)

            serial_no = ace.get("serialNo")

            def _auto_release_worker(targets, s_no):
                if s_no is None:
                    logger.warning("[!] Remote Verify solicitado, mas serialNo nao veio no evento.")
                    return

                for ip in targets:
                    logger.info(f"[*] Tentando liberar {ip} via RemoteCheck (Serial: {s_no})...")
                    success, _, _ = do_remote_verify(ip, s_no)
                    if success:
                        return

            threading.Thread(target=_auto_release_worker, args=(ips_to_try, serial_no), daemon=True).start()
        elif is_verify_request and not remote_verify_enabled:
            logger.info("[*] Remote Verify solicitado, mas 'Verificacao Remota' esta DESATIVADA.")

    status_code = 200 if ack_enabled else 500
    log_event(request.path, request.method, client_ip, data, status_code, log_to_file=True, event_source="facial")

    image_file = _first_uploaded_image(("facePic", "faceImage", "FaceImage", "FacePic"))
    image_url = _save_uploaded_file(image_file, "event")
    if image_url and events_log:
        events_log[-1]["image_url"] = image_url

    return "", status_code


def start_server():
    port = server_config.get("port", 8080)
    host = get_effective_server_host()
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    port = server_config.get("port", 8080)
    host = get_effective_server_host()
    interface_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"[*] Iniciando {APP_NAME} em {host}:{port}")
    print(f"[*] Configuracao: {server_config}")

    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    if webview is None:
        print(f"[*] Interface web: http://{interface_host}:{port}")
        t.join()
    else:
        webview.create_window(APP_NAME, f"http://{interface_host}:{port}")
        webview.start(private_mode=False, storage_path=os.path.join(BASE_DIR, "webview_data"))
