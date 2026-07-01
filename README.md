# multimo - Tester Hikvision

Servidor Flask com interface desktop/web para testar eventos Hikvision de facial/acesso e ANPR, mostrar os ultimos eventos em tempo real e salvar fotos recebidas via multipart.

## Recursos

- Recebe eventos faciais em `POST /` com multipart `event_log` + foto.
- Aceita JSON bruto e XML Hikvision como fallback.
- Recebe eventos ANPR `mixedTargetDetection` via multipart.
- Salva imagens em `captured_images`.
- Mostra contadores separados para facial/acesso e ANPR.
- Permite alternar a resposta HTTP entre `200 OK` e `500`.
- Pode liberar automaticamente eventos de acesso aprovados usando ISAPI `remoteCheck` com o `serialNo` recebido em cada evento.

## Executar

```bash
python app.py
```

A porta configurada neste checkout esta em `config.json` e foi deixada como `40800`, conforme a ultima pagina salva da versao Hikvision. A interface abre em:

```text
http://127.0.0.1:40800
```

## Configuracao

`config.json`:

```json
{
    "port": 40800,
    "ack_enabled": true,
    "device_user": "admin",
    "device_password": "password",
    "remote_verify_enabled": false
}
```

`device_user` e `device_password` sao usados quando `remote_verify_enabled` esta ligado.

## Eventos Faciais

Endpoint principal:

```text
POST /
```

Formato recomendado:

- campo multipart `event_log`: JSON do evento Hikvision
- campo multipart `facePic`, `faceImage`, `FaceImage` ou `FacePic`: imagem do evento

O servidor tambem tenta ler o primeiro campo de formulario que contenha JSON Hikvision e a primeira imagem enviada, caso o equipamento use outro nome de campo.

## ANPR

Para cameras ANPR Hikvision, envie multipart com o campo:

```text
mixedTargetDetection
```

O servidor normaliza placa, confianca, cor, marca, tipo, IP, canal e imagem do veiculo para a interface.

## API Local

- `GET /api/events`: ultimos eventos recebidos.
- `GET /api/meta`: contadores de facial/acesso e ANPR.
- `GET /api/settings`: configuracoes atuais.
- `POST /api/settings`: altera `ack_enabled`, `port`, `device_user`, `device_password` e `remote_verify_enabled`.
- `POST /api/remote_verify`: executa `remoteCheck` ISAPI com `ipAddress` e `serialNo`.

## Build Windows

```bash
pyinstaller --noconfirm --onefile --windowed --name "multimo - Tester Hikvision" --add-data "templates;templates" --hidden-import "webview" app.py
```

O executavel fica em `dist/`.
