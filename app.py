import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
import json
import os
import base64
import sys
import threading
import webview
from flask import Flask, request, jsonify, render_template, send_from_directory

# Fix for PyInstaller --onefile mode to locate templates
if getattr(sys, 'frozen', False):
    # Running in a bundle
    import sys
    base_dir = sys._MEIPASS
    template_folder = os.path.join(base_dir, 'templates')
    static_folder = os.path.join(base_dir, 'static') # assuming you might have static later
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # Running in normal python environment
    app = Flask(__name__)

# --- Configuration Management ---
CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "port": 30000,
    "image_folder": os.path.join(os.path.join(os.path.expanduser('~'), 'Desktop'), 'Tollgate_Images'),
    "save_images": True,
    "ack_enabled": True
}

server_config = {}

def load_config():
    global server_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure all keys exist
                server_config = DEFAULT_CONFIG.copy()
                server_config.update(loaded)
        except Exception as e:
            print(f"[!] Error loading config: {e}")
            server_config = DEFAULT_CONFIG.copy()
    else:
        server_config = DEFAULT_CONFIG.copy()
        save_config()

def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(server_config, f, indent=4)
        print("[*] Configuration saved.")
    except Exception as e:
        print(f"[!] Error saving config: {e}")

# Initialize Config
load_config()

# Ensure Image Folder Exists
if not os.path.exists(server_config['image_folder']):
    try:
        os.makedirs(server_config['image_folder'], exist_ok=True)
    except OSError:
        # Fallback if path is invalid
        print(f"[!] Invalid path {server_config['image_folder']}, reverting to default.")
        server_config['image_folder'] = DEFAULT_CONFIG['image_folder']
        os.makedirs(server_config['image_folder'], exist_ok=True)


# Global State
events_log = []     # Store recent events in memory
event_id_counter = 0
vehicle_counter = 0 # Count only events with valid plates

# Configure Logging
# Create logs directory
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Base logger config
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console Handler
c_handler = logging.StreamHandler()
c_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(c_handler)

# File Handler (Hourly Rotation)
# when='h', interval=1 -> Rotates every hour
# backupCount=168 -> Keep logs for 7 days (24 * 7)
log_file = os.path.join(LOG_DIR, 'lpr_server.log')
f_handler = TimedRotatingFileHandler(log_file, when='h', interval=1, backupCount=168, encoding='utf-8')
f_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
f_handler.suffix = "%Y-%m-%d_%Hh.log" # Suffix format for rotated files
logger.addHandler(f_handler)

def save_image_from_data(data):
    """
    Extracts images from the data payload, saves them to disk, 
    and returns a dictionary of relative paths (filenames).
    Modifies 'data' in place to remove large base64 strings to save memory.
    """
    saved_paths = {}
    
    if not isinstance(data, dict):
        return saved_paths

    # Check if image saving is enabled
    if not server_config.get('save_images', True):
        # We still want to remove base64 content to save memory in logs/UI
        # But we won't write to disk.
        # However, checking the logic below, it removes content ONLY if it saves.
        # We should probably strip the content anyway if we are not saving?
        # For now let's just proceed. The original logic replaced content with SAVED_TO_DISK string.
        # If we don't save, we should replace it with [NOT_SAVED] or similar to avoid memory bloat.
        pass

    picture_data = data.get('Picture', {})
    if not picture_data:
        return saved_paths

    # List of keys to check for images
    image_keys = ['NormalPic', 'CutoutPic', 'PlatePic']
    
    for key in image_keys:
        pic_info = picture_data.get(key)
        if pic_info and isinstance(pic_info, dict) and 'Content' in pic_info:
            content = pic_info['Content']
            if not content:
                continue
                
            if server_config.get('save_images', True):
                # Generate a filename
                # Prefer PicName from payload, otherwise generate one
                original_name = pic_info.get('PicName', f"{key}_{datetime.datetime.now().strftime('%H%M%S%f')}.jpg")
                
                # Ensure unique filename to prevent overwrites if names are generic
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{original_name}"
                current_image_folder = server_config.get('image_folder', DEFAULT_CONFIG['image_folder'])
                
                # Make sure folder exists (in case it was changed at runtime)
                if not os.path.exists(current_image_folder):
                    try:
                        os.makedirs(current_image_folder, exist_ok=True)
                    except:
                        pass # Should log error

                file_path = os.path.join(current_image_folder, filename)
                
                try:
                    # Decode and save
                    image_bytes = base64.b64decode(content)
                    with open(file_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    # Store the filename to be served later
                    saved_paths[key] = filename
                    
                    # Remove base64 content from memory object to save space
                    pic_info['Content'] = f"[SAVED_TO_DISK: {filename}]"
                    pic_info['HostedURL'] = f"/images/{filename}"
                    
                except Exception as e:
                    print(f"[!] Error saving image {key}: {e}")
            else:
                 # Saving disabled - strip content to save RAM
                 pic_info['Content'] = "[SAVING_DISABLED]"

    return saved_paths

def log_event(path, method, client_ip, data, status_code, log_to_file=False):
    global event_id_counter
    event_id_counter += 1
    
    # Process images before logging
    # This modifies 'data' in place, removing base64 strings
    saved_images = save_image_from_data(data)
    
    entry = {
        "id": event_id_counter,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "path": path,
        "method": method,
        "client_ip": client_ip,
        "data": data,
        "status": status_code,
        "images": saved_images # helper for frontend
    }
    events_log.append(entry)
    # Keep only last 100 events
    if len(events_log) > 100:
        events_log.pop(0)
    
    # Log using standard logging interface
    # If log_to_file is True, use logging.info (which goes to file)
    # If False, use print (console only) or logging.debug if not configured to file
    # Limitation: The current logger config sends INFO to both. 
    # To split them, we would need separate handlers or filters.
    # For simplicity: We will only call logging.info if log_to_file is True. 
    # Otherwise just print to console to avoid spamming the log file.
    
    msg = f"# RECV {method} {path} from {client_ip} | Status: {status_code}"
    if log_to_file:
         logging.info(f"{msg} | Data: {json.dumps(entry['data'], ensure_ascii=False)}")
    else:
         print(f"[{entry['timestamp']}] {msg}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve images from the configured folder."""
    return send_from_directory(server_config['image_folder'], filename)

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.json
        
        updated = False
        if 'ack_enabled' in data:
            server_config['ack_enabled'] = bool(data['ack_enabled'])
            updated = True
            
        if 'port' in data:
            try:
                p = int(data['port'])
                if 1024 <= p <= 65535:
                    server_config['port'] = p
                    updated = True
            except ValueError:
                pass
                
        if 'image_folder' in data:
            path = data['image_folder']
            if path and os.path.isdir(os.path.dirname(os.path.abspath(path))): # Basic check
                server_config['image_folder'] = path
                updated = True
                # Try create it now
                os.makedirs(path, exist_ok=True)

        if 'save_images' in data:
            server_config['save_images'] = bool(data['save_images'])
            updated = True

        if updated:
            save_config()
            
    return jsonify(server_config)

@app.route('/api/meta', methods=['GET'])
def get_meta():
    """Return metadata like counters."""
    return jsonify({"vehicle_count": vehicle_counter})

@app.route('/api/events', methods=['GET'])
def get_events():
    return jsonify(events_log)

# --- DAHUA LPR Routes ---

@app.route('/NotificationInfo/TollgateInfo', methods=['POST'])
def tollgate_info():
    global vehicle_counter
    
    ack_enabled = server_config.get('ack_enabled', True)
    
    try:
        data = request.json
        if not data:
             data = {}
    except Exception:
        # If not JSON, try to read raw but it's hard to parse without a schema. 
        # We'll just store a raw marker.
        data = {"raw": request.data.decode(errors='ignore')}

    client_ip = request.remote_addr
    
    # Check for valid plate
    has_valid_plate = False
    try:
        plate_number = data.get('Picture', {}).get('Plate', {}).get('PlateNumber')
        if plate_number and plate_number != "unknown" and plate_number != "":
            has_valid_plate = True
            vehicle_counter += 1
    except:
        pass

    if ack_enabled:
        status_code = 200
        # Common DAHUA response for success
        response_data = {"Result": True, "Message": "Success"}
    else:
        status_code = 500
        response_data = {"Result": False, "Message": "Simulated Error"}

    # Log event
    # Only write to file if it is a valid plate passage event (based on user request)
    log_to_file = has_valid_plate
    
    log_event(request.path, request.method, client_ip, data, status_code, log_to_file=log_to_file)
    
    return jsonify(response_data), status_code

@app.route('/NotificationInfo/DeviceInfo', methods=['POST'])
def device_info():
    ack_enabled = server_config.get('ack_enabled', True)
    
    try:
        data = request.json
        if not data:
            data = {}
    except Exception:
        data = {}
        
    client_ip = request.remote_addr
    
    if ack_enabled:
        status_code = 200
        response_data = {"Result": True, "Message": "Success"}
    else:
        status_code = 500
        response_data = {"Result": False, "Message": "Simulated Error"}

    # Keep-alives usually don't need persistent file logging unless debugging
    log_event(request.path, request.method, client_ip, data, status_code, log_to_file=False)
    return jsonify(response_data), status_code

@app.route('/notification', methods=['POST'])
@app.route('/keepalive', methods=['POST'])
@app.route('/NotificationInfo/KeepAlive', methods=['POST'])
def notification_keepalive():
    """
    Handle recurring keepalive/heartbeat messages.
    Expected response is often empty JSON {} with 200 OK.
    """
    ack_enabled = server_config.get('ack_enabled', True)
    
    try:
        data = request.json
        if not data:
             data = {}
    except Exception:
        data = {}
    
    client_ip = request.remote_addr

    if ack_enabled:
        status_code = 200
        response_data = {} # Empty JSON object
    else:
        status_code = 500
        response_data = {"Result": False, "Message": "Simulated Error"}

    log_event(request.path, request.method, client_ip, data, status_code, log_to_file=False)
    
    return jsonify(response_data), status_code

def start_server():
    port = server_config.get('port', 30000)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    port = server_config.get('port', 30000)
    print(f"[*] Starting LPR Server on port {port}")
    print(f"[*] Config: {server_config}")
    
    # Run the server in a separate thread
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    # Open the GUI window
    webview.create_window("LPR Server Interface", f"http://127.0.0.1:{port}")
    webview.start()
