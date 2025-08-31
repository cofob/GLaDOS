# GLaDOS Remote Audio Setup

This guide explains how to deploy GLaDOS on a remote server and consume microphone data from remote devices.

## 🎯 Overview

The remote audio functionality allows you to:
- Deploy GLaDOS on a remote server
- Connect multiple remote devices to stream microphone data
- Process speech recognition and generate responses remotely
- Play audio responses back to remote clients

## 🏗️ Architecture

```
┌─────────────────┐    WebSocket   ┌──────────────────┐    HTTP    ┌─────────────────┐
│  Remote Device  │ ◄────────────► │  GLaDOS Server   │ ◄────────► │  LLM (Ollama)   │
│    (Client)     │      Audio     │                  │    API     │                 │
│                 │    Streaming   │                  │            │                 │
│ • Microphone    │                │ • WebSocket      │            │ • llama3.2      │
│ • Speakers      │                │ • HTTP API       │            │                 │
│ • Client Script │                │ • ASR/TTS        │            │                 │
└─────────────────┘                └──────────────────┘            └─────────────────┘
```

## 🚀 Quick Start

### 1. Setup the Server

Run the automated setup script:

```bash
./scripts/setup_remote_glados.sh setup
```

This will:
- Check Docker and Docker Compose
- Create configuration files
- Build and start the GLaDOS remote service
- Install client dependencies
- Show usage instructions

### 2. Connect from Remote Device

On the client machine, install dependencies:

```bash
pip install sounddevice websockets numpy loguru
```

Run the client script:

```bash
python examples/remote_audio_client.py --server ws://YOUR_SERVER_IP:8765
```

Replace `YOUR_SERVER_IP` with your server's IP address.

## 🔧 Manual Setup

### Server Configuration

1. **Environment Configuration**
   Create `.env.remote`:
   ```bash
   API_PORT=5050
   WS_PORT=8765
   GLADOS_CONFIG=/app/configs/remote_config.yaml
   OLLAMA_URL=http://host.docker.internal:11434
   ```

2. **GLaDOS Configuration**
   Edit `configs/remote_config.yaml`:
   ```yaml
   Glados:
     audio_io: "remote"  # Use remote audio backend
     asr_engine: "tdt"   # ASR engine
     voice: "glados"     # TTS voice
     # ... other settings
   
   RemoteAudio:
     ws_port: 8765       # WebSocket port
     vad_threshold: 0.8  # Voice activity detection
     max_clients: 10     # Maximum concurrent clients
   ```

3. **Start Services**
   ```bash
   docker compose -f docker-compose.remote.yml up --build -d
   ```

### Client Setup

1. **Install Dependencies**
   ```bash
   pip install sounddevice websockets numpy loguru
   ```

2. **List Audio Devices**
   ```bash
   python examples/remote_audio_client.py --list-devices
   ```

3. **Connect to Server**
   ```bash
   python examples/remote_audio_client.py --server ws://SERVER_IP:8765 --device DEVICE_INDEX
   ```

## 📡 Network Configuration

### Ports Used

- **5050**: HTTP API for TTS and other services
- **8765**: WebSocket for real-time audio streaming
- **11434**: Ollama LLM service (if running locally)

### Firewall Rules

Allow incoming connections on the required ports:

```bash
# UFW example
sudo ufw allow 5050/tcp
sudo ufw allow 8765/tcp
sudo ufw allow 11434/tcp  # Only if running Ollama locally
```

### SSL/TLS Configuration

For production deployment, consider adding SSL/TLS:

1. **Reverse Proxy Setup**
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       # WebSocket proxy
       location /ws/ {
           proxy_pass http://localhost:8765;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
       }
       
       # HTTP API proxy
       location / {
           proxy_pass http://localhost:5050;
       }
   }
   ```

2. **Update Client Connection**
   ```bash
   python examples/remote_audio_client.py --server wss://your-domain.com/ws/
   ```

## 🔍 Monitoring and Management

### Service Status

```bash
./scripts/setup_remote_glados.sh status
```

### View Logs

```bash
./scripts/setup_remote_glados.sh logs
```

### Test Connection

```bash
./scripts/setup_remote_glados.sh test
```

### Stop Services

```bash
./scripts/setup_remote_glados.sh stop
```

## 🎛️ Configuration Options

### Server Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ws_port` | WebSocket port for audio streaming | 8765 |
| `vad_threshold` | Voice activity detection threshold (0.0-1.0) | 0.8 |
| `max_clients` | Maximum concurrent remote clients | 10 |
| `sample_rate` | Audio sample rate in Hz | 16000 |
| `chunk_size` | Audio chunk size in samples | 1024 |

### Client Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--server` | WebSocket server URL | `ws://localhost:8765` |
| `--device` | Audio input device index | System default |
| `--sample-rate` | Audio sample rate | 16000 |
| `--chunk-size` | Audio chunk size | 1024 |

## 🐛 Troubleshooting

### Common Issues

1. **Connection Refused**
   - Check if server is running: `./scripts/setup_remote_glados.sh status`
   - Verify firewall settings
   - Ensure correct IP address

2. **Audio Device Issues**
   - List available devices: `python examples/remote_audio_client.py --list-devices`
   - Check microphone permissions
   - Verify audio device is not in use

3. **No Speech Recognition**
   - Check VAD threshold in configuration
   - Verify audio levels are adequate
   - Check server logs for errors

4. **High Latency**
   - Reduce `chunk_size` for lower latency
   - Check network connection quality
   - Consider server resources

### Debug Mode

Enable debug logging:

```bash
# Server
docker compose -f docker-compose.remote.yml logs -f glados-remote

# Client
python examples/remote_audio_client.py --server ws://localhost:8765 --debug
```

## 📊 Performance Considerations

### Server Requirements

- **CPU**: Multi-core processor for ASR/TTS processing
- **RAM**: 4GB minimum, 8GB recommended
- **Network**: Stable internet connection with sufficient bandwidth
- **Storage**: 2GB for models and logs

### Client Requirements

- **CPU**: Modern processor for real-time audio processing
- **RAM**: 2GB minimum
- **Network**: Low-latency connection to server
- **Audio**: Compatible microphone and speakers

### Bandwidth Usage

- **Audio Streaming**: ~256 kbps per client
- **Protocol Overhead**: ~10% additional bandwidth
- **Concurrent Clients**: Scale based on server capacity

## 🔒 Security Considerations

### Network Security

1. **Firewall Configuration**
   - Only expose necessary ports
   - Use IP whitelisting for trusted clients
   - Consider VPN for private networks

2. **Authentication**
   - Implement API key authentication
   - Use WebSocket authentication tokens
   - Consider client certificate authentication

3. **Data Encryption**
   - Use SSL/TLS for all connections
   - Encrypt audio data in transit
   - Secure configuration files

### Privacy

- Audio data is processed in real-time
- No audio data is stored by default
- Consider data retention policies for compliance

## 🚀 Advanced Usage

### Multiple Servers

For high availability, deploy multiple GLaDOS instances:

```yaml
# docker-compose.scale.yml
services:
  glados-remote-1:
    extends:
      file: docker-compose.remote.yml
      service: glados-remote
    environment:
      - WS_PORT=8765
  
  glados-remote-2:
    extends:
      file: docker-compose.remote.yml
      service: glados-remote
    environment:
      - WS_PORT=8766
```

### Load Balancing

Use a load balancer to distribute clients across servers:

```nginx
upstream glados_backend {
    server server1:8765;
    server server2:8766;
    server server3:8767;
}

server {
    listen 8765;
    location / {
        proxy_pass http://glados_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Custom Audio Processing

Extend the remote audio system:

```python
# Custom audio processor
class CustomAudioProcessor:
    def process_audio(self, audio_data):
        # Add custom processing
        processed_audio = self.apply_filter(audio_data)
        return processed_audio

# Integrate with RemoteAudioIO
remote_io = RemoteAudioIO()
remote_io.audio_processor = CustomAudioProcessor()
```

## 📝 API Reference

### WebSocket Protocol

#### Client to Server Messages

```json
{
  "type": "audio",
  "data": [0.1, 0.2, 0.3, ...]
}
```

```json
{
  "type": "ping"
}
```

#### Server to Client Messages

```json
{
  "type": "config",
  "sample_rate": 16000,
  "chunk_size": 1024,
  "format": "float32"
}
```

```json
{
  "type": "audio_playback",
  "data": [0.1, 0.2, 0.3, ...],
  "sample_rate": 22050,
  "text": "Hello from GLaDOS"
}
```

```json
{
  "type": "pong"
}
```

### HTTP API Endpoints

- `POST /v1/audio/speech` - Generate speech from text
- `GET /health` - Health check endpoint

## 🤝 Contributing

To contribute to the remote audio functionality:

1. Test with various network conditions
2. Report performance issues
3. Suggest configuration improvements
4. Submit bug reports and feature requests

## 📄 License

This project is licensed under the same terms as the main GLaDOS project.

---

For additional support, please refer to the main GLaDOS documentation or create an issue in the project repository.
