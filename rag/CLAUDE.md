# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **VASP RAG (Retrieval-Augmented Generation) system** with advanced parallel processing capabilities. The system processes VASP Wiki documentation and provides intelligent Q&A using Ollama-based language models with a custom dynamic load balancer.

### Core Components

1. **`vasp_rag_advanced.py`** - Main RAG system with:
   - `RAGConfig` - Configuration management (supports env vars)
   - `RemoteOllamaConfig` - Multi-server Ollama management
   - `RealTimeLoadBalancer` - Dynamic load balancing ("who's idle does the work")
   - `VASPRAGAdvanced` - Core RAG pipeline class

2. **`final_processor.py`** - Data preprocessing utility for cleaning VASP Wiki JSON data

3. **Data files**:
   - `vasp_wiki_all_data.json` - Raw scraped VASP Wiki data
   - `vasp_wiki_all_data_readable.json` - Processed/cleaned data
   - `chroma_db/` - Persistent vector database (created at runtime)

## Architecture

### Dynamic Load Balancing Strategy
The system implements a unique **real-time load balancer** that:
- Pre-creates embedding clients for all available servers
- Each server has its own lock and busy state flag
- Tasks wait for any idle server (no pre-allocation)
- Fast servers naturally handle more tasks (complete → immediately take new task)
- Provides real-time performance statistics

### RAG Pipeline Flow
```
1. Server Discovery → Check all Ollama servers, find embedding models
2. Data Loading → Load JSON documents
3. Document Splitting → RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
4. Parallel Embedding → RealTimeLoadBalancer generates embeddings across servers
5. Vector Storage → ChromaDB persistence
6. Retrieval → Similarity search (k=5)
7. Generation → ChatOllama with custom prompt template
```

## Common Commands

### Development & Testing
```bash
# Test Ollama server connections
python vasp_rag_advanced.py server

# Run full pipeline (requires real data and Ollama servers)
python vasp_rag_advanced.py pipeline

# Run demo with 30 documents (fast test)
python vasp_rag_advanced.py test

# Demonstrate load balancing behavior
python vasp_rag_advanced.py demo

# Process/clean raw VASP Wiki data
python final_processor.py
```

### Environment Variables (Optional)
```bash
# Server configuration
VASP_SERVER_HOSTS="localhost,192.168.1.130,192.168.1.127"
VASP_SERVER_PORT=11434
VASP_SERVER_TIMEOUT=3

# Performance tuning
VASP_MAX_WORKERS=4
VASP_CHUNK_SIZE=1000
VASP_CHUNK_OVERLAP=200
VASP_BATCH_SIZE=20

# Model selection
VASP_CHAT_MODEL="qwen3:4b-instruct-2507-q4_K_M"
VASP_PERSIST_DIR="./chroma_db"

# Test queries (comma-separated or JSON array)
VASP_TEST_QUERIES="什么是 RPA 计算？,ALGO 参数有哪些选项？"
VASP_DATA_FILE="vasp_wiki_all_data_readable.json"
```

## Key Features

### 1. Multi-Server Support
- Automatically discovers available Ollama servers
- Finds best embedding model across all servers
- Supports failover and retry logic

### 2. Parallel Processing
- Thread-based parallelism for embedding generation
- Batch processing with configurable batch sizes
- Real-time progress tracking with tqdm

### 3. Data Preprocessing
The `final_processor.py` script:
- Unescapes `\n`, `\t`, `\"` characters
- Removes "Retrieved from" metadata
- Formats warnings/tips/notes with emojis
- Wraps VASP INCAR parameters in code blocks
- Cleans up excessive whitespace

### 4. RAG Query System
- Custom prompt template for VASP expertise
- Retrieves 5 most relevant documents
- Generates detailed Chinese responses with technical details

## File Structure
```
rag/
├── vasp_rag_advanced.py    # Main RAG system (1194 lines)
├── final_processor.py       # Data cleaner (151 lines)
├── vasp_wiki_all_data.json  # Raw data (~5.9MB)
├── vasp_wiki_all_data_readable.json  # Cleaned data (~5.7MB)
├── chroma_db/               # Created at runtime (vector store)
├── chroma_db_demo/          # Created by demo mode
└── .claude/                 # Claude Code settings
```

## Important Notes

### Dependencies
Requires Python packages:
- `langchain-*` (text_splitters, ollama, chroma, core)
- `requests` (server health checks)
- `tqdm` (progress bars)
- `chromadb` (vector database)

### Server Requirements
- Ollama servers must be running on configured hosts/ports
- Embedding models (qwen3-embedding, nomic-embed-text, etc.) must be pulled
- Chat model (qwen3:4b-instruct-2507-q4_K_M) must be available

### Demo Mode
The `test` command uses only 30 documents and skips server checks, making it ideal for quick validation without full infrastructure.

### Load Balancer Behavior
The `RealTimeLoadBalancer` is the key innovation - it doesn't use static assignment. Instead, it:
1. Maintains a pool of embedder clients with individual locks
2. Each batch waits for any available server
3. Updates global stats for performance monitoring
4. Naturally favors faster servers (they become available sooner)