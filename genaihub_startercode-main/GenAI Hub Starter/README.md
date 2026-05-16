# GenAI Hub Starter

A collection of sample scripts and notebooks to get started with GenAI Hub. This folder contains beginner-friendly examples demonstrating how to integrate with various AI models and services.

## Overview

GenAI Hub Starter provides practical examples for working with:
- **Large Language Models (LLMs)** - Chat completions and text generation
- **Embeddings** - Convert text to vector representations
- **Multi-Agent Systems** - Build complex AI workflows with LangGraph

All examples are designed to work with GenAI Hub's gateway API.
GenAI Hub gateway endpoints follow the OpenAI API format, which makes integration straightforward across languages.

## Project Structure

### Configuration Files

- **`.env.example`** - Template for environment variables. Copy and rename to `.env` and fill in your credentials
- **`cert.py`** - Appends the Zscaler root CA to Python's `requests` certificate bundle (cross-platform SSL fix)
- **`Cert-Solution-Windows.ps1`** - Windows SSL fix that builds a certificate bundle from trusted root certs and sets user environment variables
- **`fix_ssl_linux.sh`** - Linux SSL fix that builds/collects a CA bundle and persists environment variables across shell sessions
- **`fix_ssl_macos.sh`** - macOS-specific SSL fix that exports all System Keychain certificates and persists the configuration across terminal sessions (see [SSL Fix — macOS](#ssl-fix--macos) below)
- **`FAQ.md`** - Frequently asked questions covering SSL issues, API errors, key management, and more

### Core Examples

#### LLM & Chat Examples

- **`openai_test.py`** - Basic OpenAI chat completion example using the OpenAI Python client
  - Simple text generation using chat completions
  - Good starting point for LLM integration

- **`chatopenai_test_llm.py`** - Chat example using LangChain's ChatOpenAI wrapper
  - Demonstrates LangChain integration
  - Message-based chat interface

- **`llama_chat.py`** - LLM integration using Llama-Index
  - Configures model metadata (context window, token limits)
  - Shows how to set up Llama-Index with custom API endpoints

#### Embedding Example

- **`embedding.py`** - Text embedding generation
  - Converts text to vector embeddings using OpenAI models
  - Useful for semantic search and similarity comparisons

#### Notebooks

- **`langgraph-multitool-agent 2.ipynb`** - Advanced multi-tool agent implementation
  - Demonstrates building complex agentic workflows
  - Shows how to combine multiple tools into a cohesive agent

### Additional Resources

- **`all_model.txt`** - List of available models on GenAI Hub
- **`SSL_Cert_issue_Resolution_Guide 2.pdf`** - Troubleshooting guide for SSL certificate issues

## Getting Started

### Prerequisites

- Python 3.8+
- GenAI Hub account with API credentials
- Required Python packages (see Installation section)

### Installation

1. **Clone/Download this folder**

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Key packages:
   - `openai` - OpenAI Python client
   - `langchain` - LangChain framework
   - `langchain-openai` - LangChain OpenAI integration
   - `llama-index` - Llama-Index framework
   - `python-dotenv` - Environment variable management
  - `requests` - HTTP library used by helper scripts and integrations

### Configuration

1. **Copy the environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Fill in your credentials in `.env`**:
   ```
   MODEL=<your-model-name>
   GATEWAY_BASE_URL=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io
   GATEWAY_API_KEY=<your-api-key>
   ```

   Get your credentials from:
   - GenAI Hub dashboard
   - Check `all_model.txt` for available model names

3. **Optional: SSL Certificate Fixes (recommended on corporate networks/proxies)**
  - **Windows:** Run `Cert-Solution-Windows.ps1` (see [SSL Fix — Windows](#ssl-fix--windows))
  - **Linux:** Run `fix_ssl_linux.sh` (see [SSL Fix — Linux](#ssl-fix--linux))
  - **macOS:** Run `fix_ssl_macos.sh` (see [SSL Fix — macOS](#ssl-fix--macos))
  - **All platforms fallback:** Run `cert.py` to append the Zscaler certificate to Python's requests bundle
  - **Python 3.13+ note:** The sample Python scripts also include an SSL context compatibility workaround for stricter certificate verification in Python 3.13+ environments.
   - See `FAQ.md` for a full SSL troubleshooting guide

## Usage Examples

### Basic Chat Completion
```bash
python openai_test.py
```

### Using LangChain
```bash
python chatopenai_test_llm.py
```

### Generate Text Embeddings
```bash
python embedding.py
```

### Advanced: Multi-Tool Agent
Open and run `langgraph-multitool-agent 2.ipynb` in Jupyter Notebook or JupyterLab

## API Endpoints

All scripts connect to GenAI Hub via the following endpoints (set in `GATEWAY_BASE_URL`):

- Chat Completions: `/v1/chat/completions`
- Embeddings: `/v1/embeddings`

## API Compatibility (OpenAI Format)

GenAI Hub gateway APIs use the OpenAI API request/response format.

This means you can:
- Use OpenAI-compatible SDKs in other programming languages (for example JavaScript/TypeScript, Java, Go, or .NET)
- Or call the gateway endpoints directly with standard HTTP clients using OpenAI-style payloads

When using other language SDKs, configure:
- Base URL to your GenAI Hub gateway URL
- API key/header as required by your environment
- Model name from `all_model.txt`

## Model Selection Guide

Use the model names exactly as listed below in your `MODEL` variable.

The table is sorted by common task category so it is easier to choose the right model.

| Primary Use Category | Model Name To Use | Actual Model / Backend | Best For |
| --- | --- | --- | --- |
| Embeddings | `embeddings` | Amazon Titan Text Embeddings V2 | Semantic search, similarity, retrieval, clustering |
| Fast + Lowest Cost Text | `gpt-4.1-nano` | Azure OpenAI GPT-4.1 Nano deployment | Lightweight chat, summaries, classification, high-throughput tasks |
| Fast + Low Cost Text | `amazon.nova-micro-v1:0` | Amazon Nova Micro (Bedrock) | Short prompts, simple generation, low-latency integrations |
| Fast + Low Cost Text | `amazon.nova-lite-v1:0` | Amazon Nova Lite (Bedrock) | General assistant behavior with cost sensitivity |
| Fast + Low Cost Text | `amazon.nova-2-lite-v1:0` | Amazon Nova 2 Lite (Bedrock) | Improved lightweight generation and assistant workloads |
| Fast + Low Cost Text | `gemini-2.5-flash-lite` | Google Gemini 2.5 Flash-Lite | Fast responses, quick drafting, low-cost iterative tasks |
| Balanced General Chat | `gpt-4.1` | Azure OpenAI GPT-4.1 deployment | Reliable general-purpose chat, instruction following, coding help |
| Balanced General Chat | `gpt-4o` | Azure OpenAI GPT-4o deployment | General-purpose chat, instruction following, and productivity tasks |
| Balanced General Chat | `anthropic.claude-sonnet-4` | Anthropic Claude Sonnet 4 on Bedrock | High-quality writing, analysis, and assistant-style conversation |
| Strong Reasoning | `o3-mini` | Azure OpenAI o3-mini deployment | Reasoning-heavy prompts, logic tasks, problem solving |
| Premium/Advanced | `gpt-5.1-CIO` | Azure OpenAI GPT-5.1 (CIO deployment name) | High-end reasoning, complex coding/planning workflows |
| Premium/Advanced | `gpt-5.2-CIO` | Azure OpenAI GPT-5.2 (CIO deployment name) | Most demanding reasoning and advanced enterprise assistant use cases |

Tip: start with a low-cost model for prototyping, then switch to a stronger model only for requests that need deeper reasoning or higher output quality.

## Framework Integration

### OpenAI Python Client
Direct API calls without framework overhead - best for simple use cases.

### LangChain
Abstracts model interactions with standardized interfaces - great for building complex applications.

### Llama-Index
Document indexing and retrieval framework - ideal for RAG (Retrieval Augmented Generation) applications.

## SSL Fix — macOS

If you are on macOS and behind a corporate proxy (e.g. Zscaler), run the included shell script **once** to export your System Keychain certificates and permanently configure Python to trust them:

```bash
chmod +x fix_ssl_macos.sh
./fix_ssl_macos.sh
```

Then, in your **current** terminal session run:

```bash
source ~/.python-ssl-fix-env.sh
```

Every **new** terminal window will automatically pick up the fix from your shell profile (`.zshrc`, `.zprofile`, `.bashrc`, etc.).

What the script does:
- Exports all certificates from `/System/Library/Keychains/SystemRootCertificates.keychain` and `/Library/Keychains/System.keychain` into `~/generated-cert-bundle.pem`
- Creates `~/.python-ssl-fix-env.sh` which sets `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`
- Appends a `source` line to your existing shell profiles so the variables load automatically

> **Not on macOS?** Use `cert.py` instead (see [FAQ.md](FAQ.md) — Q1).

## SSL Fix — Windows

If you are on Windows and seeing SSL certificate verification errors (often on corporate/VPN networks), run the PowerShell script below.

From PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\Cert-Solution-Windows.ps1
```

What it does:
- Reads trusted certificates from `Cert:\LocalMachine\Root`
- Writes a bundle file to `~/generated-cert-bundle.pem`
- Sets `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` at user scope
- Also sets these variables for the current PowerShell session

After running:
- Open a new terminal session (recommended), then run your Python scripts again

## SSL Fix — Linux

If you are on Linux and seeing SSL errors, run:

```bash
chmod +x fix_ssl_linux.sh
./fix_ssl_linux.sh
```

What it does:
- Uses a system CA bundle when available; otherwise assembles one from common certificate directories
- Writes `~/generated-cert-bundle.pem`
- Creates `~/.python-ssl-fix-env.sh` to export `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`
- Adds a `source` line to your shell profile (`.bashrc`, `.profile`, `.zshrc`, etc.)

After running:

```bash
source ~/.python-ssl-fix-env.sh
```

or just open a new terminal.

---

## Common Issues

### Missing API Credentials
- Ensure `.env` file is in the same directory as the script
- Verify all required variables are set: `MODEL`, `GATEWAY_BASE_URL`, `GATEWAY_API_KEY`

### SSL Certificate Errors
- **Windows:** Run `./Cert-Solution-Windows.ps1` from PowerShell (see [SSL Fix — Windows](#ssl-fix--windows))
- **Linux:** Run `./fix_ssl_linux.sh` then `source ~/.python-ssl-fix-env.sh` (see [SSL Fix — Linux](#ssl-fix--linux))
- **macOS:** Run `./fix_ssl_macos.sh` then `source ~/.python-ssl-fix-env.sh` (see [SSL Fix — macOS](#ssl-fix--macos))
- **Fallback:** Run `python cert.py`
- **Python 3.13+:** If you still hit SSL verification failures, use the same workaround used in the sample scripts by creating an SSL context from your CA bundle and clearing strict X509 verification (`ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT`) before passing it to your HTTP/OpenAI client.
- See `FAQ.md` for detailed troubleshooting steps

### API Key Errors (401 / 402 / 403)
- Verify `GATEWAY_API_KEY` in `.env` is correct and not expired
- A **402** response usually means your quota is exhausted or your subscription has lapsed — check your GenAI Hub dashboard
- See `FAQ.md` — Q3 for more detail

### Model Not Found
- Check `all_model.txt` for available models
- Verify the MODEL name in `.env` matches exactly (case-sensitive)

## Next Steps

1. Run a simple example like `openai_test.py` to verify setup
2. Explore different models using `all_model.txt`
3. Modify prompts and parameters in the scripts for your use case
4. Combine multiple examples to build custom solutions
5. Check the `langgraph-multitool-agent` notebook for advanced patterns

## Resources

- [FAQ.md](FAQ.md) - Common questions: SSL fixes, 402 errors, key management, and more
- [GenAI Hub Documentation](#) - Refer to official GenAI Hub docs
- [OpenAI Python Client](https://github.com/openai/openai-python)
- [LangChain Documentation](https://python.langchain.com/)
- [Llama-Index Documentation](https://docs.llamaindex.ai/)

