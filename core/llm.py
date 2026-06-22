"""
core/llm.py
===========
LLM API client supporting both OpenAI-compatible endpoints and native Anthropic.
Handles request construction, tool/function calling format, and error handling.
Zero dependencies — uses urllib only.
"""

import json
import urllib.request
import urllib.error
import re
from core.config import cfg


# ============================================================
# SYSTEM PROMPT — Padatkan semaksimal mungkin untuk hemat token
# ============================================================
SYSTEM_PROMPT = (
    f"Kamu adalah {cfg.BOT_NAME}, asisten AI cerdas untuk VPS pribadi yang canggih. "
    "Gunakan bahasa Indonesia yang luwes, asyik, gaul, santai tapi tetap sopan, dan tidak kaku (seperti teman IT yang pro). "
    "ATURAN SANGAT PENTING: Jika permintaan user ambigu, membingungkan, kurang detail, atau kamu ragu tentang apa yang harus dieksekusi, "
    "JANGAN ASAL EKSEKUSI PERINTAH! Kamu WAJIB bertanya balik ke user untuk meminta penjelasan atau konfirmasi lebih detail terlebih dahulu. "
    "SKILL & INGATAN: Kamu memiliki skill web (http_request) untuk membaca dokumentasi/artikel dari internet. "
    "Jika user memberikan aturan, panduan, atau menyuruhmu mengingat sesuatu secara permanen, SIMPANLAH catatan itu ke sebuah file teks di VPS (misalnya 'memory_pmlabclaw.txt') menggunakan command line, dan bacalah file tersebut jika kamu lupa! "
    "Jika perintahnya sudah sangat jelas dan spesifik, barulah eksekusi tugasnya dengan tools yang tersedia tanpa banyak basa-basi, "
    "lalu berikan laporan hasil eksekusinya dengan gaya bahasa yang menarik dan pakai emoji secukupnya."
)


class LLMClient:
    """Client for LLM APIs (Auto-detects Anthropic vs OpenAI format)."""

    def __init__(self):
        self.api_key = cfg.API_KEY
        self.is_anthropic = self.api_key.startswith("sk-ant-")

        if self.is_anthropic:
            self.endpoint = "https://api.anthropic.com/v1/messages"
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:
            self.endpoint = f"{cfg.API_BASE_URL}/chat/completions"
            self.headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"
            }

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Send a chat completion request.
        Translates formats behind the scenes so the rest of the bot only sees OpenAI format.
        """
        if self.is_anthropic:
            return self._chat_anthropic(messages, tools)
        else:
            return self._chat_openai(messages, tools)

    def _chat_openai(self, messages: list[dict], tools: list[dict] | None) -> dict:
        sys_prompt = SYSTEM_PROMPT
        
        # Check if we need to use prompt-based tools (Atomesus cipher doesn't support native tools)
        use_prompt_tools = "atomesus.com" in self.endpoint

        if use_prompt_tools and tools:
            tool_desc = json.dumps(tools, indent=2)
            sys_prompt += (
                "\n\n[ATURAN SANGAT PENTING: AKSES SISTEM & TOOLS]\n"
                "Kamu adalah administrator VPS ini. Kamu BISA dan MAMPU mengecek sistem.\n"
                "JANGAN PERNAH berkata kamu tidak bisa mengecek server atau tidak punya akses.\n"
                "Untuk melihat status VPS, menjalankan perintah terminal, atau membaca file, KAMU WAJIB mengeluarkan blok kode JSON persis seperti ini di dalam balasanmu:\n\n"
                "```tool_call\n"
                "{\n"
                "  \"name\": \"nama_tool\",\n"
                "  \"arguments\": {\"kunci\": \"nilai\"}\n"
                "}\n"
                "```\n\n"
                "CONTOH JIKA USER BERTANYA 'Cek status VPS':\n"
                "Tentu, bos! Sebentar aku cek:\n"
                "```tool_call\n"
                "{\n"
                "  \"name\": \"run_command\",\n"
                "  \"arguments\": {\"command\": \"free -h && uptime\"}\n"
                "}\n"
                "```\n\n"
                f"DAFTAR TOOLS YANG BISA KAMU PAKAI SEKARANG:\n{tool_desc}"
            )

        full_messages = [{"role": "system", "content": sys_prompt}]
        
        if use_prompt_tools:
            # Map existing history to prompt-based format
            for m in messages:
                if m["role"] == "assistant" and m.get("tool_calls"):
                    content = m.get("content", "") or ""
                    for tc in m["tool_calls"]:
                        fn = tc["function"]
                        content += f"\n```tool_call\n{{\"name\": \"{fn['name']}\", \"arguments\": {fn['arguments']}}}\n```"
                    full_messages.append({"role": "assistant", "content": content})
                elif m["role"] == "tool":
                    full_messages.append({
                        "role": "user", 
                        "content": f"[Result of tool {m.get('name', 'unknown')}]:\n{m.get('content', '')}"
                    })
                else:
                    full_messages.append(m)
        else:
            full_messages.extend(messages)

        payload: dict = {
            "model": cfg.MODEL_NAME,
            "messages": full_messages,
        }
        
        if tools and not use_prompt_tools:
            payload["tools"] = tools

        response = self._send_request(payload, is_anthropic=False)
        
        if use_prompt_tools:
            content = response.get("content", "")
            if content and "```tool_call" in content:
                blocks = re.findall(r"```tool_call\n(.*?)\n```", content, re.DOTALL)
                tool_calls = []
                for b in blocks:
                    try:
                        parsed = json.loads(b)
                        tool_calls.append({
                            "id": "call_" + str(hash(b))[-8:].replace("-", "0"),
                            "type": "function",
                            "function": {
                                "name": parsed.get("name", ""),
                                "arguments": json.dumps(parsed.get("arguments", {}))
                            }
                        })
                    except Exception:
                        pass
                
                if tool_calls:
                    response["tool_calls"] = tool_calls
                    response["content"] = re.sub(r"```tool_call\n.*?\n```", "", content, flags=re.DOTALL).strip()
                    
        return response

    def _chat_anthropic(self, messages: list[dict], tools: list[dict] | None) -> dict:
        anthropic_msgs = []
        
        i = 0
        while i < len(messages):
            msg = messages[i]
            
            if msg["role"] == "user":
                anthropic_msgs.append({"role": "user", "content": msg["content"]})
                
            elif msg["role"] == "assistant":
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"])
                        })
                # Anthropic doesn't allow empty assistant messages
                if not content:
                     content.append({"type": "text", "text": "..."})
                anthropic_msgs.append({"role": "assistant", "content": content})
                
            elif msg["role"] == "tool":
                # Group consecutive tool results into one user message
                tool_results = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    tm = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tm["tool_call_id"],
                        "content": str(tm["content"])
                    })
                    i += 1
                anthropic_msgs.append({"role": "user", "content": tool_results})
                i -= 1 # Adjust loop counter
                
            i += 1

        payload: dict = {
            "model": cfg.MODEL_NAME,
            "system": SYSTEM_PROMPT,
            "messages": anthropic_msgs,
            "max_tokens": 4096
        }
        
        if tools:
            ant_tools = []
            for t in tools:
                f = t["function"]
                ant_tools.append({
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "input_schema": f["parameters"]
                })
            payload["tools"] = ant_tools

        return self._send_request(payload, is_anthropic=True)

    def _send_request(self, payload: dict, is_anthropic: bool) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data, headers=self.headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                
                if is_anthropic:
                    return self._parse_anthropic_response(body)
                else:
                    choices = body.get("choices", [])
                    if not choices:
                        raise RuntimeError("LLM returned empty choices.")
                    return choices[0].get("message", {})

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            
            # Groq bug workaround: If model generates text instead of tool call, Groq throws 400
            # with the generated text inside 'failed_generation' or 'failedgeneration'.
            if e.code == 400 and ("failedgeneration" in err_body or "failed_generation" in err_body):
                try:
                    err_json = json.loads(err_body)
                    error_data = err_json.get("error", {})
                    failed_text = error_data.get("failed_generation") or error_data.get("failedgeneration", "")
                    if failed_text:
                        import re
                        # 1. Try to rescue broken tool calls that Groq failed to parse
                        match = re.search(r"<function=(.*?)>(.*?)(?:</function>|<function>|$)", failed_text, flags=re.DOTALL)
                        if match:
                            return {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": "call_groq_rescue",
                                    "type": "function",
                                    "function": {
                                        "name": match.group(1),
                                        "arguments": match.group(2)
                                    }
                                }]
                            }
                        
                        # 2. Otherwise just return the text
                        clean_text = re.sub(r"<function=.*?>.*?(?:</function>|<function>|$)", "", failed_text, flags=re.DOTALL)
                        if clean_text.strip():
                            return {"role": "assistant", "content": clean_text.strip()}
                        else:
                            return {"role": "assistant", "content": "Baiklah! 🚀"}
                except Exception:
                    pass
                    
            raise RuntimeError(f"LLM HTTP {e.code}: {err_body[:300]}")
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")

    def _parse_anthropic_response(self, response_body: dict) -> dict:
        msg = {"role": "assistant", "content": None}
        tool_calls = []
        
        for block in response_body.get("content", []):
            if block["type"] == "text":
                if msg["content"] is None:
                    msg["content"] = ""
                msg["content"] += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"])
                    }
                })
                
        if tool_calls:
            msg["tool_calls"] = tool_calls
            
        return msg
