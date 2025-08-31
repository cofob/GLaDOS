"""Audio input/output components.

This package provides an abstraction layer for audio input and output operations,
allowing the Glados engine to work with different audio backends interchangeably.

Classes:
    AudioProtocol: Abstract interface for audio input/output operations
    SoundDeviceAudioIO: Implementation using the sounddevice library
    RemoteAudioIO: Implementation using WebSockets for remote audio streaming

Functions:
    get_audio_system: Factory function to create AudioProtocol instances
"""

import queue
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .vad import VAD


class AudioProtocol(Protocol):
    def __init__(self, vad_threshold: float | None = None) -> None: ...
    def start_listening(self) -> None: ...
    def stop_listening(self) -> None: ...
    def start_speaking(
        self, audio_data: NDArray[np.float32], sample_rate: int | None = None, text: str = ""
    ) -> None: ...
    def measure_percentage_spoken(self, total_samples: int, sample_rate: int | None = None) -> tuple[bool, int]: ...
    def check_if_speaking(self) -> bool: ...
    def stop_speaking(self) -> None: ...
    def get_sample_queue(self) -> queue.Queue[tuple[NDArray[np.float32], bool]]: ...


# Factory function
def get_audio_system(backend_type: str = "sounddevice", vad_threshold: float | None = None, **kwargs) -> AudioProtocol:
    """
    Factory function to get an instance of an audio I/O system based on the specified backend type.

    Parameters:
        backend_type (str): The type of audio backend to use:
            - "sounddevice": Uses the sounddevice library for local audio I/O
            - "remote": Uses WebSockets for remote audio streaming from clients
        vad_threshold (float | None): Optional threshold for voice activity detection
        **kwargs: Additional parameters for specific backends:
            - For "remote": ws_port (int) - WebSocket port for audio streaming

    Returns:
        AudioProtocol: An instance of the requested audio I/O system

    Raises:
        ValueError: If the specified backend type is not supported
    """
    if backend_type == "sounddevice":
        from .sounddevice_io import SoundDeviceAudioIO

        return SoundDeviceAudioIO(
            vad_threshold=vad_threshold,
        )
    elif backend_type == "remote":
        from .remote_io import RemoteAudioIO

        ws_port = kwargs.get("ws_port", 8765)
        return RemoteAudioIO(
            vad_threshold=vad_threshold,
            ws_port=ws_port
        )
    else:
        raise ValueError(f"Unsupported audio backend type: {backend_type}")


__all__ = [
    "VAD",
    "AudioProtocol",
    "get_audio_system",
]
