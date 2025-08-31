#!/usr/bin/env python3
"""
Remote Audio Client for GLaDOS

This script connects to a GLaDOS server running in remote audio mode
and streams microphone data to it for speech recognition and processing.

Usage:
    python remote_audio_client.py --server ws://localhost:8765 --device 0
"""

import argparse
import asyncio
import json
import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd
import websockets
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger.remove()
logger.add(lambda msg: print(msg, end=""), level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


class RemoteAudioClient:
    """Client for streaming audio to a remote GLaDOS server."""

    def __init__(
        self,
        server_url: str,
        device: Optional[int] = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        vad_threshold: float = 0.8,
    ):
        """Initialize the remote audio client.

        Args:
            server_url: WebSocket URL of the GLaDOS server
            device: Audio input device index (default: None for system default)
            sample_rate: Audio sample rate (default: 16000)
            chunk_size: Number of samples per chunk (default: 1024)
            vad_threshold: Voice Activity Detection threshold (default: 0.8)
        """
        self.server_url = server_url
        self.device = device
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.vad_threshold = vad_threshold
        
        self.websocket = None
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.is_connected = False
        self.stop_event = threading.Event()
        
        # Audio stream
        self.input_stream = None
        
        # Configuration received from server
        self.server_config = {}

    async def connect(self) -> bool:
        """Connect to the GLaDOS server.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to GLaDOS server at {self.server_url}...")
            
            self.websocket = await websockets.connect(
                self.server_url,
                max_size=None,
                compression=None,
                ping_interval=30,
                ping_timeout=10
            )
            
            # Wait for configuration from server
            config_message = await self.websocket.recv()
            config_data = json.loads(config_message)
            
            if config_data.get("type") == "config":
                self.server_config = config_data
                self.sample_rate = config_data.get("sample_rate", self.sample_rate)
                self.chunk_size = config_data.get("chunk_size", self.chunk_size)
                
                logger.info(f"Connected to server. Configuration received:")
                logger.info(f"  Sample rate: {self.sample_rate} Hz")
                logger.info(f"  Chunk size: {self.chunk_size} samples")
                logger.info(f"  Format: {config_data.get('format', 'float32')}")
                
                self.is_connected = True
                return True
            else:
                logger.error("Unexpected first message from server")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            return False

    def start_audio_capture(self) -> bool:
        """Start capturing audio from the microphone.

        Returns:
            bool: True if audio capture started successfully, False otherwise
        """
        try:
            logger.info(f"Starting audio capture from device {self.device or 'default'}...")
            
            def audio_callback(indata, frames, time, status):
                """Callback for audio input."""
                if status:
                    logger.warning(f"Audio callback status: {status}")
                
                # Convert to float32 and add to queue
                audio_data = np.array(indata).copy().squeeze()
                self.audio_queue.put(audio_data)
            
            self.input_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=audio_callback,
                blocksize=self.chunk_size,
                device=self.device
            )
            
            self.input_stream.start()
            logger.info("Audio capture started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}")
            return False

    async def send_audio_loop(self):
        """Main loop for sending audio data to the server."""
        logger.info("Starting audio streaming...")
        
        # Start ping/pong for connection health
        ping_task = asyncio.create_task(self._ping_pong_loop())
        
        try:
            while self.is_running and self.is_connected:
                try:
                    # Get audio data from queue with timeout
                    try:
                        audio_data = self.audio_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    
                    # Send audio data to server
                    audio_message = {
                        "type": "audio",
                        "data": audio_data.tolist()
                    }
                    
                    await self.websocket.send(json.dumps(audio_message))
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection to server closed")
                    break
                except Exception as e:
                    logger.error(f"Error sending audio data: {e}")
                    break
                    
        finally:
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

    async def _ping_pong_loop(self):
        """Send periodic ping messages to keep connection alive."""
        while self.is_running and self.is_connected:
            try:
                await asyncio.sleep(15)  # Ping every 15 seconds
                if self.is_connected:
                    await self.websocket.send(json.dumps({"type": "ping"}))
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"Error in ping/pong loop: {e}")
                break

    async def receive_messages(self):
        """Handle messages received from the server."""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get("type") == "pong":
                        # Server responded to ping
                        pass
                    elif data.get("type") == "audio_playback":
                        # Server wants us to play audio
                        await self._handle_audio_playback(data)
                    elif data.get("type") == "stop_playback":
                        # Server wants us to stop playback
                        self._stop_audio_playback()
                    elif data.get("type") == "error":
                        logger.error(f"Server error: {data.get('message')}")
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Server connection closed")
        except Exception as e:
            logger.error(f"Error in message receiver: {e}")

    async def _handle_audio_playback(self, data):
        """Handle audio playback request from server."""
        try:
            audio_data = np.array(data["data"], dtype=np.float32)
            sample_rate = data.get("sample_rate", self.sample_rate)
            text = data.get("text", "")
            
            logger.info(f"Playing audio: {text}")
            
            # Play audio using sounddevice
            sd.play(audio_data, sample_rate)
            sd.wait()  # Wait for playback to complete
            
        except Exception as e:
            logger.error(f"Error playing audio: {e}")

    def _stop_audio_playback(self):
        """Stop current audio playback."""
        sd.stop()
        logger.info("Audio playback stopped")

    def stop(self):
        """Stop the client and clean up resources."""
        logger.info("Stopping remote audio client...")
        self.is_running = False
        self.stop_event.set()
        
        # Stop audio stream
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None
        
        # Close WebSocket connection
        if self.websocket:
            asyncio.create_task(self.websocket.close())
        
        self.is_connected = False
        logger.info("Remote audio client stopped")

    async def run(self):
        """Run the remote audio client."""
        self.is_running = True
        
        # Connect to server
        if not await self.connect():
            logger.error("Failed to connect to server")
            return
        
        # Start audio capture
        if not self.start_audio_capture():
            logger.error("Failed to start audio capture")
            await self.websocket.close()
            return
        
        # Start message receiver
        receive_task = asyncio.create_task(self.receive_messages())
        
        # Start audio sending loop
        send_task = asyncio.create_task(self.send_audio_loop())
        
        try:
            # Wait for tasks to complete or stop event
            await asyncio.gather(receive_task, send_task)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.stop()
            
            # Cancel tasks
            for task in [receive_task, send_task]:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass


def list_audio_devices():
    """List available audio input devices."""
    logger.info("Available audio input devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            logger.info(f"  {i}: {device['name']} (inputs: {device['max_input_channels']})")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Remote Audio Client for GLaDOS")
    parser.add_argument(
        "--server", 
        default="ws://localhost:8765",
        help="WebSocket URL of GLaDOS server (default: ws://localhost:8765)"
    )
    parser.add_argument(
        "--device", 
        type=int, 
        default=None,
        help="Audio input device index (default: system default)"
    )
    parser.add_argument(
        "--sample-rate", 
        type=int, 
        default=16000,
        help="Audio sample rate (default: 16000)"
    )
    parser.add_argument(
        "--chunk-size", 
        type=int, 
        default=1024,
        help="Audio chunk size (default: 1024)"
    )
    parser.add_argument(
        "--list-devices", 
        action="store_true",
        help="List available audio devices and exit"
    )
    
    args = parser.parse_args()
    
    if args.list_devices:
        list_audio_devices()
        return
    
    client = RemoteAudioClient(
        server_url=args.server,
        device=args.device,
        sample_rate=args.sample_rate,
        chunk_size=args.chunk_size
    )
    
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    except Exception as e:
        logger.error(f"Client error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
