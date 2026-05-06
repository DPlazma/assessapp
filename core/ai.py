"""
Shared AI helper — single place for all provider calls.
"""
import json
import urllib.request
import urllib.error


def ai_chat(prompt, *, max_tokens=2000, timeout=60, system=None):
    """
    Send a chat-completion request to the configured AI provider.

    Returns (reply_text, error_string).  Exactly one will be non-empty.
    """
    from core.models import AISettings

    ai = AISettings.load()
    if not ai.enabled or ai.provider == "none":
        return "", "AI is not configured."

    endpoint = ai.endpoint_url.rstrip("/") if ai.endpoint_url else ""
    model = ai.model_name or "gpt-3.5-turbo"

    # ── Build URL ────────────────────────────────────────────────
    if ai.provider == "openai":
        url = (endpoint or "https://api.openai.com/v1") + "/chat/completions"
    elif ai.provider in ("azure", "copilot"):
        if not endpoint:
            return "", f"{ai.get_provider_display()} requires an Endpoint URL."
        url = endpoint + f"/openai/deployments/{model}/chat/completions?api-version=2024-02-01"
    elif ai.provider == "gemini":
        url = (endpoint or "https://generativelanguage.googleapis.com/v1beta") + \
            f"/models/{model}:generateContent"
    elif ai.provider == "ollama":
        url = (endpoint or "http://localhost:11434") + "/api/chat"
    elif ai.provider == "custom":
        if not endpoint:
            return "", "Custom provider requires an Endpoint URL."
        url = endpoint + "/chat/completions"
    else:
        return "", "Unknown provider."

    # ── Build payload & headers ──────────────────────────────────
    headers = {"Content-Type": "application/json"}

    if ai.provider == "gemini":
        parts = []
        if system:
            parts.append({"text": system + "\n\n" + prompt})
        else:
            parts.append({"text": prompt})
        payload = json.dumps({
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }).encode()
        if ai.api_key:
            url += ("&" if "?" in url else "?") + f"key={ai.api_key}"
    else:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if ai.provider == "ollama":
            data["stream"] = False
        payload = json.dumps(data).encode()
        if ai.api_key:
            if ai.provider in ("azure", "copilot"):
                headers["api-key"] = ai.api_key
            else:
                headers["Authorization"] = f"Bearer {ai.api_key}"

    # ── Send request ─────────────────────────────────────────────
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        return "", f"HTTP {e.code}: {detail}"
    except urllib.error.URLError as e:
        return "", f"Connection failed: {e.reason}"
    except Exception as e:
        return "", str(e)[:200]

    # ── Parse response ───────────────────────────────────────────
    reply = ""
    if "choices" in body:
        reply = body["choices"][0].get("message", {}).get("content", "")
    elif "message" in body:
        reply = body["message"].get("content", "")
    elif "candidates" in body:
        parts = body["candidates"][0].get("content", {}).get("parts", [])
        reply = parts[0].get("text", "") if parts else ""

    if not reply:
        return "", "AI returned an empty response."

    return reply.strip(), ""
