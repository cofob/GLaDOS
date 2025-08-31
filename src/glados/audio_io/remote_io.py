import asyncio
import json
import queue
import threading
import time
from typing import Any, Dict, Optional
import websockets
from loguru import logger
import numpy as np
from numpy.typing import NDArray

from . import VAD


class RemoteAudioIO:
    """Audio I/O implementation for remote microphone streaming via WebSocket.

    This class provides an implementation that allows remote devices to stream
    audio data to GLaDOS through WebSocket connections. It handles real-time
    audio capture with voice activity detection and supports multiple concurrent
    remote clients.
    """

    SAMPLE_RATE: int = 16000  # Sample rate for input stream
    VAD_SIZE: int = 32  # Milliseconds of sample for Voice Activity Detection (VAD)
    VAD_THRESHOLD: float = 0.8  # Threshold for VAD detection
    WS_PORT: int = 8765  # WebSocket port for audio streaming
    MAX_CLIENTS: int = 10  # Maximum concurrent clients
    AUDIO_CHUNK_SIZE: int = 1024  # Number of samples per audio chunk

    def __init__(self, vad_threshold: float | None = None, ws_port: int | None = None) -> None:
        """Initialize the remote audio I/O system.

        Args:
            vad_threshold: Threshold for VAD detection (default: 0.8)
            ws_port: WebSocket port for audio streaming (default: 8765)
        """
        if vad_threshold is None:
            self.vad_threshold = self.VAD_THRESHOLD
        else:
            self.vad_threshold = vad_threshold

        if ws_port is None:
            self.ws_port = self.WS_PORT
        else:
            self.ws_port = ws_port

        if not 0 <= self.vad_threshold <= 1:
            raise ValueError("VAD threshold must be between 0 and 1")

        self._vad_model = VAD()
        self._sample_queue: queue.Queue[tuple[NDArray[np.float32], bool]] = queue.Queue()
        self._is_listening = False
        self._is_playing = False
        self._stop_event = threading.Event()
        self._ws_server = None
        self._ws_thread = None
        self._clients: set = set()
        self._client_lock = threading.Lock()

    def start_listening(self) -> None:
        """Start the WebSocket server for remote audio streaming.

        Creates and starts a WebSocket server that accepts connections from
        remote devices and streams audio data for processing.
        """
        if self._is_listening:
            return

        self._is_listening = True
        self._stop_event.clear()
        
        # Start WebSocket server in a separate thread
        self._ws_thread = threading.Thread(target=self._run_ws_server, daemon=True)
        self._ws_thread.start()
        
        logger.success(f"Remote audio server started on port {self.ws_port}")
        logger.success("Waiting for remote microphone connections...")

    def _run_ws_server(self) -> None:
        """Run the WebSocket server in a separate thread."""
        async def handle_client(websocket, path):
            """Handle individual client connections."""
            client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
            logger.info(f"Remote client connected: {client_id}")
            
            with self._client_lock:
                if len(self._clients) >= self.MAX_CLIENTS:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Server at maximum capacity"
                    }))
                    await websocket.close()
                    return
                
                self._clients.add(websocket)

            try:
                # Send configuration to client
                await websocket.send(json.dumps({
                    "type": "config",
                    "sample_rate": self.SAMPLE_RATE,
                    "chunk_size": self.AUDIO_CHUNK_SIZE,
                    "format": "float32"
                }))

                # Handle incoming audio data
                async for message in websocket:
                    if self._stop_event.is_set():
                        break
                    
                    try:
                        data = json.loads(message)
                        if data.get("type") == "audio":
                            # Process audio data
                            audio_data = np.array(data["data"], dtype=np.float32)
                            if len(audio_data) > 0:
                                # Apply VAD
                                vad_value = self._vad_model(np.expand_dims(audio_data, 0))
                                vad_confidence = vad_value > self.vad_threshold
                                self._sample_queue.put((audio_data, bool(vad_confidence)))
                        
                        elif data.get("type") == "ping":
                            # Respond to ping for connection health check
                            await websocket.send(json.dumps({"type": "pong"}))

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Error processing message from {client_id}: {e}")
                        continue

            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Client disconnected: {client_id}")
            except Exception as e:
                logger.error(f"Error handling client {client_id}: {e}")
            finally:
                with self._client_lock:
                    self._clients.discard(websocket)

        # Start WebSocket server
        async def server_wrapper():
            self._ws_server = await websockets.serve(
                handle_client,
                "0.0.0.0",
                self.ws_port,
                max_size=None,  # Allow large messages
                compression=None  # Disable compression for low latency
            )
            logger.info(f"WebSocket server started on ws://0.0.0.0:{self.ws_port}")
            
            # Keep server running until stop event
            while not self._stop_event.is_set():
                await asyncio.sleep(0.1)

        # Run the server
        asyncio.run(server_wrapper())

    def stop_listening(self) -> None:
        """Stop the WebSocket server and clean up resources."""
        if not self._is_listening:
            return

        self._is_listening = False
        self._stop_event.set()

        # Close all client connections
        with self._client_lock:
            for client in self._clients.copy():
                try:
                    asyncio.create_task(client.close())
                except:
                    pass
            self._clients.clear()

        # Stop WebSocket server
        if self._ws_server:
            asyncio.create_task(self._ws_server.close())

        # Wait for WebSocket thread to finish
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)

        logger.info("Remote audio server stopped")

    def start_speaking(self, audio_data: NDArray[np.float32], sample_rate: int | None = None, text: str = "") -> None:
        """Play audio through remote clients.

        Parameters:
            audio_data: The audio data to play as a numpy float32 array
            sample_rate: The sample rate of the audio data in Hz
            text: Optional text associated with the audio
        """
        if not isinstance(audio_data, np.ndarray) or audio_data.size == 0:
            raise ValueError("Invalid audio data")

        if sample_rate is None:
            sample_rate = self.SAMPLE_RATE

        # Stop any existing playback
        self.stop_speaking()

        logger.debug(f"Broadcasting audio to {len(self._clients)} remote clients")
        self._is_playing = True

        # Send audio data to all connected clients
        with self._client_lock:
            if not self._clients:
                logger.warning("No remote clients connected for audio playback")
                self._is_playing = False
                return

            # Convert audio to list for JSON serialization
            audio_list = audio_data.tolist()
            
            # Create audio message
            audio_message = {
                "type": "audio_playback",
                "data": audio_list,
                "sample_rate": sample_rate,
                "text": text
            }

            # Broadcast to all clients
            disconnected_clients = set()
            for client in self._clients:
                try:
                    asyncio.create_task(client.send(json.dumps(audio_message)))
                except:
                    disconnected_clients.add(client)

            # Remove disconnected clients
            for client in disconnected_clients:
                self._clients.discard(client)

        # Simulate playback duration
        playback_duration = len(audio_data) / sample_rate
        threading.Timer(playback_duration, self._on_playback_complete).start()

    def _on_playback_complete(self) -> None:
        """Called when audio playback is complete."""
        self._is_playing = False

    def measure_percentage_spoken(self, total_samples: int, sample_rate: int | None = None) -> tuple[bool, int]:
        """Monitor audio playback progress for remote clients.

        Args:
            total_samples: Total number of samples in the audio data being played
            sample_rate: Sample rate of the audio

        Returns:
            tuple[bool, int]: (interrupted, percentage_played)
        """
        if sample_rate is None:
            sample_rate = self.SAMPLE_RATE

        # For remote playback, we simulate progress
        # In a real implementation, you might track actual playback status from clients
        interrupted = not self._is_playing
        percentage_played = 100 if not self._is_playing else 0
        
        return interrupted, percentage_played

    def check_if_speaking(self) -> bool:
        """Check if audio is currently being played to remote clients.

        Returns:
            bool: True if audio is currently playing, False otherwise
        """
        return self._is_playing

    def stop_speaking(self) -> None:
        """Stop audio playback to remote clients."""
        if self._is_playing:
            self._is_playing = False
            
            # Send stop signal to all clients
            with self._client_lock:
                stop_message = {"type": "stop_playback"}
                disconnected_clients = set()
                
                for client in self._clients:
                    try:
                        asyncio.create_task(client.send(json.dumps(stop_message)))
                    except:
                        disconnected_clients.add(client)
                
                # Remove disconnected clients
                for client in disconnected_clients:
                    self._clients.discard(client)

    def get_sample_queue(self) -> queue.Queue[tuple[NDArray[np.float32], bool]]:
        """Get the queue containing audio samples and VAD confidence.

        Returns:
            queue.Queue: A thread-safe queue containing tuples of
                        (audio_sample, vad_confidence)
        """
        return self._sample_queue

    def get_connected_clients(self) -> int:
        """Get the number of currently connected remote clients.

        Returns:
            int: Number of connected clients
        """
        return len(self._clients)
