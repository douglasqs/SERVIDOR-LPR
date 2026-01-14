# DAHUA LPR Event Server

A desktop application and web server designed to receive, process, and display License Plate Recognition (LPR) events from Dahua cameras. This application provides a real-time dashboard to monitor vehicle passages and saves captured images locally.

## 🚀 Features

- **LPR Event Handling**: Receives HTTP POST requests with JSON payloads from Dahua LPR cameras.
- **Image Processing**: Automatically decodes Base64 images (Normal, Cutout, Plate) and saves them to `Desktop/Tollgate_Images`.
- **Real-time Dashboard**: A modern web interface displaying the latest events, vehicle counts, and server status.
- **Desktop Application**: Runs as a standalone desktop window using `pywebview` (no browser required).
- **Connection Simulation**: Toggle ensuring "200 OK" or "500 Error" responses to test camera behavior when the server is down/busy.
- **Keep-Alive Support**: Handles heartbeat messages from cameras to maintain connection status.

## 🛠️ Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/lpr-server.git
    cd lpr-server
    ```

2.  **Install Dependencies**:
    Requires Python 3.x. Install the necessary packages:
    ```bash
    pip install -r requirements.txt
    ```
    *(If `requirements.txt` doesn't exist, install manually)*:
    ```bash
    pip install Flask pywebview
    ```

## 🖥️ Usage

### Running Locally
To start the application:

```bash
python app.py
```

- Information on the console will show the server port (default: `30000`).
- A window will automatically open with the dashboard.
- Images will be saved to your Desktop in the `Tollgate_Images` folder.

### Building as Executable (.exe)
To compile the application into a single `.exe` file for Windows:

1.  Install PyInstaller:
    ```bash
    pip install pyinstaller
    ```

2.  Run the build command:
    ```bash
    pyinstaller --noconfirm --onefile --windowed --name "LPR_Server" --add-data "templates;templates" --hidden-import "webview" app.py
    ```
    *Note: The `--add-data` flag is crucial for including the HTML interface inside the executable.*

3.  The output file will be in the `dist/` folder.

## 📡 API Endpoints

-   `POST /NotificationInfo/TollgateInfo`: Main endpoint for vehicle passage events.
-   `POST /NotificationInfo/KeepAlive`: Status check from cameras.
-   `GET /api/events`: Returns the history of recent events (JSON).
-   `POST /api/settings`: Toggle the ACK (Response Mode) status.

## 📂 Project Structure

-   `app.py`: Main server logic, image decoding, and GUI launcher.
-   `templates/index.html`: Frontend dashboard.
-   `Desktop/Tollgate_Images`: Default storage location for captured images.

## 📝 License

[MIT License](LICENSE)
