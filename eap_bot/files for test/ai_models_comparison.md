# AI Companies & Models — Full Comparison + Python Implementation Reference
*Compiled Aug 2026. Model names/pricing shift monthly — verify against official docs before an interview or production use.*

## 1. Master Comparison Table

| Company | Flagship Model | Mid/Small Models | Context Window | Python Package | Auth Method | API Style | Key Strength |
|---|---|---|---|---|---|---|---|
| OpenAI | GPT-5.6 (Sol) | GPT-5.5, GPT-5.2, o4-mini | ~1M+ tokens | `openai` | `OPENAI_API_KEY` env var | Native (Chat Completions / Responses) | Reasoning, tool-calling, structured JSON |
| Anthropic | Claude Opus (4.8 / 5) | Claude Sonnet 4.6/5, Claude Haiku 4.5 | 200K–1M tokens | `anthropic` | `ANTHROPIC_API_KEY` env var | Native (Messages API) | Long-doc comprehension, coding, careful reasoning |
| Google | Gemini 3.1/3.5 Pro | Gemini 3.5 Flash, Flash-Lite | Up to 2M tokens | `google-genai` | `GOOGLE_API_KEY` / Vertex ADC | Native (`generate_content`) | Multimodal, largest context, search grounding |
| Meta | Muse Spark 1.1 | Llama 4 Scout (open) | Varies | `openai` (compat) or HF | API key / self-host | OpenAI + Anthropic compatible | Agentic tool-use, self-hostable |
| xAI | Grok 4.5 | Grok 4, Grok 3, Grok 3-fast | 128K–256K | `openai` (compat) or `xai_sdk` | `XAI_API_KEY` env var | OpenAI-compatible + native Responses API | Real-time data via X, live search |
| DeepSeek | DeepSeek V4-pro | DeepSeek V4-flash | Large | `openai` (compat) | `DEEPSEEK_API_KEY` env var | OpenAI-compatible | Very cheap, strong reasoning per dollar |
| Mistral | Mistral Large | Mistral Medium, Small, Pixtral | Moderate | `mistralai` | `MISTRAL_API_KEY` env var | Native (`chat.complete`) | Efficient, EU-hosted, open-weight options |
| Alibaba | Qwen-Max/Plus | Qwen-Coder, Qwen-VL | Large | `openai` (compat) or `dashscope` | `DASHSCOPE_API_KEY` env var | OpenAI + native DashScope | Cheap, strong math, open weights |
| Cohere | Command R+ | Command R | Moderate | `cohere` or `openai` (compat) | `CO_API_KEY` env var | Native + OpenAI-compatible | Enterprise RAG/search |
| Groq (hosting) | Llama/Mixtral/etc | — | Model-dependent | `groq` or `openai` (compat) | `GROQ_API_KEY` env var | OpenAI-compatible | Extreme inference speed |
| Microsoft | MAI-Thinking-1 | MAI-Code-1 (in Copilot) | Moderate | Azure `openai` SDK | Azure key / AD token | Azure OpenAI-compatible | First in-house trained-from-scratch model |
| Moonshot AI | Kimi K3 (2.8T params) | — | Large | `openai` (compat) | API key | OpenAI-compatible | Largest open-weights release |

---

## 2. Python Implementation Per Provider

### OpenAI
```python
from openai import OpenAI
client = OpenAI(api_key="OPENAI_API_KEY")

response = client.chat.completions.create(
    model="gpt-5.6",
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...],              # function calling
    response_format={"type": "json_schema", "json_schema": {...}},
    temperature=0.7,
)
print(response.choices[0].message.content)
```
**JSON response shape:**
```json
{
  "choices": [{"message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0}
}
```
**Supported features:** streaming, function/tool calling, structured JSON outputs (json_schema), vision (image input), audio in/out, reasoning-effort control, web_search_options (built-in search), parallel tool calls, logprobs, seed for determinism, batch API, fine-tuning, embeddings, moderation endpoint.

---

### Anthropic (Claude)
```python
import anthropic
client = anthropic.Anthropic(api_key="ANTHROPIC_API_KEY")

message = client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello, Claude"}],
    tools=[...],               # tool use
)
for block in message.content:
    if block.type == "text":
        print(block.text)
```
**JSON response shape:**
```json
{
  "id": "msg_01XFDU...",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "Hello!"}],
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 12, "output_tokens": 6}
}
```
**Supported features:** streaming, tool use (client + server-side), vision (image input), PDF/document input, prompt caching, extended thinking, message batches, citations, Files API, computer use, code execution tool, `stop_reason: "refusal"` handling, MCP connector support, stateless Messages API (full history resent each call).

---

### Google (Gemini)
```python
from google import genai
from google.genai import types

client = genai.Client(api_key="GOOGLE_API_KEY")

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="What is the weather in Boston?",
    config=types.GenerateContentConfig(
        tools=[get_current_weather],   # automatic function calling
        temperature=0.7,
    ),
)
print(response.text)
```
**JSON response shape:**
```json
{
  "candidates": [{"content": {"parts": [{"text": "..."}], "role": "model"}}],
  "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0}
}
```
**Supported features:** automatic function calling (AFC), multimodal input/output (text, image, audio, video), code execution tool, grounding via Google Search, 2M-token context (largest available), Vertex AI + AI Studio dual access, streaming, MCP support (experimental), embeddings, batch mode.

---

### Meta (Llama / Muse Spark)
```python
from openai import OpenAI
client = OpenAI(api_key="META_API_KEY", base_url="https://api.llama.com/v1")

response = client.chat.completions.create(
    model="muse-spark-1.1",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```
**Supported features:** OpenAI- and Anthropic-compatible SDK formats (base-URL swap), agentic tool-use, self-hosting (open weights via Hugging Face for Llama line), fine-tuning on open weights, no proprietary lock-in.

---

### xAI (Grok)
```python
from openai import OpenAI
client = OpenAI(api_key="XAI_API_KEY", base_url="https://api.x.ai/v1")

response = client.chat.completions.create(
    model="grok-4.5",
    messages=[{"role": "system", "content": "You are Grok."},
              {"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```
**Supported features:** OpenAI-compatible Chat Completions + native Responses API, live/real-time search (X data), code execution tool, image generation (`images.generate`), file search over vector stores, reasoning-effort control, streaming.

---

### DeepSeek
```python
from openai import OpenAI
client = OpenAI(api_key="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1")

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0.7,
    max_tokens=1024,
)
print(response.choices[0].message.content)
```
**Supported features:** full OpenAI-compatible schema, chat prefix completion (force output format, e.g. force code block start), reasoning model variant (deepseek-reasoner style chain-of-thought), streaming, JSON output, Anthropic-format endpoint also available (`/anthropic`), very low cost per token.

---

### Mistral
```python
from mistralai import Mistral
client = Mistral(api_key="MISTRAL_API_KEY")

response = client.chat.complete(
    model="mistral-large-latest",
    messages=[{"role": "user", "content": "Who is the best French painter?"}],
    tools=[...],
    tool_choice="auto",
)
print(response.choices[0].message.content)
```
**Supported features:** function calling (`tool_choice`: none/auto/any/required), structured outputs, vision (Pixtral models), predicted outputs, embeddings, streaming, JSON mode, multi-turn Conversations API for agents.

---

### Alibaba (Qwen / DashScope)
```python
from openai import OpenAI
client = OpenAI(
    api_key="DASHSCOPE_API_KEY",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)

response = client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "system", "content": "You are a helpful assistant."},
              {"role": "user", "content": "Who are you?"}],
)
print(response.model_dump_json())
```
**Supported features:** OpenAI-compatible Responses + native DashScope protocol + Anthropic-compatible Messages endpoint, built-in web search/code interpreter (Responses mode), function calling, vision (Qwen-VL), coding-specialized variant (Qwen-Coder), math-specialized reasoning, open-weight self-hosting.

---

### Cohere
```python
from openai import OpenAI
client = OpenAI(api_key="CO_API_KEY", base_url="https://api.cohere.ai/compatibility/v1")

response = client.chat.completions.create(
    model="command-r-plus",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```
**Supported features:** OpenAI Compatibility API (drop-in SDK swap), native Cohere SDK for RAG-specific features (citations, document grounding), structured outputs, streaming, embeddings (multilingual), rerank endpoint for search relevance.

---

### Groq (inference host, various open models)
```python
import openai
client = openai.OpenAI(api_key="GROQ_API_KEY", base_url="https://api.groq.com/openai/v1")

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```
**Supported features:** OpenAI-compatible, extremely fast token throughput (custom LPU hardware), hosts multiple open-weight model families, streaming, function calling (model-dependent).

---

### Microsoft (Azure OpenAI + MAI models)
```python
from openai import AzureOpenAI
client = AzureOpenAI(
    api_key="AZURE_OPENAI_KEY",
    azure_endpoint="https://<resource>.openai.azure.com",
    api_version="2026-01-01",
)

response = client.chat.completions.create(
    model="mai-thinking-1",   # deployment name
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```
**Supported features:** Azure AD / key-based auth, enterprise compliance (SOC2, HIPAA options), content filtering layer, first in-house-trained (not distilled) reasoning model (MAI-Thinking-1), MAI-Code-1 embedded in GitHub Copilot, same Chat Completions schema as OpenAI.

---

## 3. Quick Feature Legend
- **Tool/function calling** — model can call your Python functions with structured arguments.
- **Structured outputs / JSON mode** — model guaranteed to return valid JSON matching a schema.
- **Vision** — accepts image input.
- **Streaming** — tokens returned incrementally instead of waiting for the full response.
- **OpenAI-compatible** — you can reuse the `openai` Python package, just swap `base_url` and `api_key`.

## 4. For Your Interview
When asked "how would you pick a model for this DT platform," the strongest answer is: **wrap every provider behind the same internal interface** (since most are now OpenAI-schema-compatible), so the platform can swap vendors per-solution without rewriting business logic — this is literally the "flexibility in model choice" argument from the platform's separation-of-concerns design.
