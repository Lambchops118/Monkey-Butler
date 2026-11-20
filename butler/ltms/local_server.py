"""Own a separate Ollama process so memory cannot evict the chat model."""
import os
import subprocess
from urllib.parse import urlparse

import requests


def start(url):
    try:
        response = requests.get(url + '/api/tags', timeout=1)
        response.raise_for_status()
        return None  # Explicit dedicated endpoint already managed externally.
    except requests.RequestException:
        pass
    gpu = os.getenv('BUTLER_LTMS_GPU', '').strip()
    if not gpu:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,uuid', '--format=csv,noheader'],
                                capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        gpu = next((line.split(',')[1].strip() for line in result.stdout.splitlines()
                    if 'A2000' in line), '')
    if not gpu:
        raise RuntimeError('Set BUTLER_LTMS_GPU to the dedicated GPU UUID')
    env = os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES=gpu, OLLAMA_HOST=urlparse(url).netloc,
               OLLAMA_VULKAN='false', OLLAMA_MAX_LOADED_MODELS='2',
               OLLAMA_KEEP_ALIVE='-1', OLLAMA_CONTEXT_LENGTH='8192')
    return subprocess.Popen(['ollama', 'serve'], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
