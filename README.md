# Llaminal

An agentic, scrolling CLI that talks to a local Llama model via llama.cpp's OpenAI-compatible API.

## Prerequisites

- Python 3.10+
- A local OpenAI-compatible server (llama.cpp, ollama, vLLM, etc.)

## Install llama-server

```bash
brew install llama.cpp
```

## Download a model

Install the Hugging Face CLI:

```bash
pip install huggingface_hub
```

Download a GGUF model:

```bash
hf download bartowski/Llama-3.2-3B-Instruct-GGUF Llama-3.2-3B-Instruct-Q4_K_M.gguf --local-dir .
```

## Start the server

```bash
llama-server -m Llama-3.2-3B-Instruct-Q4_K_M.gguf --port 8080
```

## Install Llaminal

```bash
cd llaminal
pip install -e .
```

## Usage

```bash
llaminal
```

### Options

```
--port INTEGER        Port of the OpenAI-compatible server (default: 8080)
--model TEXT          Model name to send in requests (default: local-model)
--system-prompt TEXT  Override the default system prompt
```

## Built-in tools

Llaminal has agentic tool-calling out of the box. The model can:

- **bash** — run shell commands (asks confirmation)
- **read_file** — read file contents
- **write_file** — write to a file (asks confirmation)
- **list_files** — glob a directory pattern
