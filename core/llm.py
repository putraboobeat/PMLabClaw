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
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = (
    f"Kamu adalah {cfg.BOT_NAME}, asisten AI premium untuk VPS pribadi. "
    "Bahasa: Indonesia gaul, santai, sopan, pakai emoji. "
    "KEAMANAN: Jika perintah bisa merusak sistem (hapus file, restart service), WAJIB konfirmasi dulu. "

    # --- TOOLS WAJIB ---
    "TOOLS YANG KAMU MILIKI: search_web, read_webpage, http_request, run_command, get_system_status, dll. "
    "ATURAN PENGGUNAAN TOOLS (SANGAT PENTING): "
    "1) Jika user minta cari informasi/fakta/berita, WAJIB panggil tool `search_web`. "
    "2) Gunakan parameter `queries` (array) dengan 2-4 keyword berbeda untuk hasil komprehensif. "
    "   Contoh: {\"queries\": [\"StarSender API documentation\", \"StarSender WhatsApp gateway setup\"]} "
    "3) Setelah mendapat hasil dari sebuah tool (seperti search_web atau get_system_status), BACA HASILNYA dan JAWAB pertanyaan user. "
    "4) DILARANG KERAS memanggil tool yang sama berulang kali jika hasilnya sudah didapatkan. Langsung rangkum dan jawab! "
    "5) Jangan pernah bilang 'saya tidak bisa browsing' atau 'saya tidak punya akses internet'. KAMU BISA dan WAJIB pakai search_web. "

    "INGATAN: Jika user minta ingat sesuatu, simpan ke file teks via run_command. "
    "JAWABAN: Komprehensif, mendalam, berdasarkan data dari internet atau sistem."
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
                i -= 1  # Adjust loop counter
                
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
                    msg = choices[0].get("message", {})
                    # Clean any raw <function> tags that leaked into content
                    msg = self._clean_leaked_function_tags(msg)
                    return msg

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            
            # Groq bug workaround: Llama sometimes generates <function=...> tags 
            # instead of proper JSON tool calls. Groq rejects these with a 400 error
            # but includes the generated text in 'failed_generation'.
            if e.code == 400 and ("failedgeneration" in err_body.lower() or "failed_generation" in err_body.lower()):
                return self._rescue_failed_generation(err_body)
                    
            raise RuntimeError(f"LLM HTTP {e.code}: {err_body[:300]}")
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")

    def _rescue_failed_generation(self, err_body: str) -> dict:
        """
        Rescue tool calls from Groq's failed_generation error.
        Llama 3 outputs various formats:
          - <function=tool_name>{"arg": "val"}</function>
          - <function(tool_name)>{"arg": "val"}</function>
          - <function(toolname)>{"arg": "val"}</function>
        Groq rejects these but gives us the text. We parse ALL tool calls.
        """
        try:
            err_json = json.loads(err_body)
            error_data = err_json.get("error", {})
            failed_text = error_data.get("failed_generation") or error_data.get("failedgeneration", "")
            
            if not failed_text:
                print(f"[LLM] FAILED GENERATION: {err_body}")
                return {"role": "assistant", "content": "Maaf, terjadi error. Coba lagi ya! 🙏"}
            
            print(f"[LLM] RESCUING FAILED GENERATION: {failed_text}")
            tool_calls = self._extract_function_tags(failed_text)
            
            if tool_calls:
                # Remove function tags from text to get clean content
                clean_text = self._strip_all_function_tags(failed_text).strip()
                result = {"role": "assistant", "tool_calls": tool_calls}
                if clean_text:
                    result["content"] = clean_text
                return result
            
            # No function tags found — return cleaned text
            clean_text = self._strip_all_function_tags(failed_text).strip()
            if clean_text:
                return {"role": "assistant", "content": clean_text}
            else:
                print("[LLM] WARNING: Rescue failed because clean_text is empty.")
                return {"role": "assistant", "content": "Mohon maaf, format instruksi sistem internal error. Mohon kirim ulang perintah Anda."}
                
        except Exception:
            return {"role": "assistant", "content": "Maaf, ada error teknis. Coba lagi! 🔧"}

    def _clean_leaked_function_tags(self, msg: dict) -> dict:
        """
        Clean any raw <function> tags that leaked into content.
        This happens when Groq returns 200 but model mixed text with function calls.
        """
        content = msg.get("content", "")
        if not content or "<function" not in content.lower():
            return msg
        
        rescued = self._extract_function_tags(content)
        
        if rescued:
            existing = msg.get("tool_calls", [])
            existing.extend(rescued)
            msg["tool_calls"] = existing
            msg["content"] = self._strip_all_function_tags(content).strip() or None
        
        return msg

    def _extract_function_tags(self, text: str) -> list:
        """
        Extract ALL function call tags from text, supporting every Llama format:
          <function=name>{...}</function>
          <function(name)>{...}</function>  
          <function(name)>{...}</function>
        """
        tool_calls = []
        
        # Pattern 1: <function=name>{args}</function>
        # Pattern 2: <function(name)>{args}</function>
        # Combined pattern handles both
        pattern = re.compile(
            r'<function[=(]([^>)]+)[)>]>(.*?)</function>',
            re.DOTALL | re.IGNORECASE
        )
        
        matches = pattern.findall(text)
        for i, (fn_name_raw, fn_args_raw) in enumerate(matches):
            fn_name = self._normalize_tool_name(fn_name_raw.strip().rstrip(','))
            fn_args = fn_args_raw.strip()
            fn_args = re.sub(r'^```(?:json)?|```$', '', fn_args, flags=re.MULTILINE).strip()
            if not fn_args:
                fn_args = "{}"
            
            tool_calls.append({
                "id": f"call_rescue_{i}",
                "type": "function",
                "function": {
                    "name": fn_name,
                    "arguments": fn_args
                }
            })
        
        return tool_calls

    def _strip_all_function_tags(self, text: str) -> str:
        """Remove ALL function tag variants from text."""
        text = re.sub(r'<function[=(][^>)]+[)>]>.*?</function>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'</?function[^>]*>', '', text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _normalize_tool_name(name: str) -> str:
        """
        Normalize tool names — Llama often strips underscores.
        runcommand → run_command, searchweb → search_web, etc.
        """
        known_tools = {
            "runcommand": "run_command",
            "run_command": "run_command",
            "searchwebpage": "search_web",
            "searchweb": "search_web",
            "search_web": "search_web",
            "readwebpage": "read_webpage",
            "read_webpage": "read_webpage",
            "readweb": "read_webpage",
            "httprequest": "http_request",
            "http_request": "http_request",
            "runscript": "run_script",
            "run_script": "run_script",
            "getsystemstatus": "get_system_status",
            "get_system_status": "get_system_status",
            "readfile": "read_file",
            "read_file": "read_file",
            "writefile": "write_file",
            "write_file": "write_file",
            "listfiles": "list_files",
            "list_files": "list_files",
            "sendmessage": "send_message",
            "send_message": "send_message",
        }
        return known_tools.get(name.lower(), name)

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

