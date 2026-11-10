"""Tiny provider-agnostic LLM client (stdlib only). Anything that speaks the OpenAI chat-completions
dialect works: Gemini, Groq, OpenRouter, OpenAI, Anthropic (compat), Ollama, LM Studio, vLLM.
Swap the model by changing base_url / model / api_key_env -- no code changes."""
from __future__ import annotations
import hashlib, json, os, re, time, urllib.request, urllib.error


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, base_url, model, api_key_env="PROMO_LLM_API_KEY", cache_dir=".llm_cache", temperature=0.0,
                 timeout=90, max_retries=4, use_cache=True):
        self.base_url = base_url.rstrip("/"); self.model = model
        self.key = os.environ.get(api_key_env, "") if api_key_env else ""
        self.temperature, self.timeout, self.max_retries = temperature, timeout, max_retries
        self.cache_dir = cache_dir if use_cache else None
        if self.cache_dir: os.makedirs(self.cache_dir, exist_ok=True)
        self.usage = {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def _post(self, payload):
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    @staticmethod
    def extract_json(text):
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            if not m: raise LLMError("no JSON object in reply: " + text[:200])
            return json.loads(m.group(0))

    def chat_json(self, system, user, required=()):
        key = hashlib.sha256(json.dumps([self.model, system, user]).encode()).hexdigest()[:24]
        path = os.path.join(self.cache_dir, key + ".json") if self.cache_dir else None
        if path and os.path.exists(path):
            self.usage["cached"] += 1
            with open(path) as fh: return json.load(fh)
        payload = {"model": self.model, "temperature": self.temperature,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "response_format": {"type": "json_object"}}
        last = None
        for attempt in range(self.max_retries):
            try:
                try:
                    resp = self._post(payload)
                except urllib.error.HTTPError as e:
                    if e.code == 400 and "response_format" in payload:   # some providers reject json mode
                        payload.pop("response_format"); resp = self._post(payload)
                    else:
                        raise
                msg = resp["choices"][0]["message"]["content"]
                data = self.extract_json(msg)
                miss = [k for k in required if k not in data]
                if miss: raise LLMError(f"missing keys {miss}")
                u = resp.get("usage", {})
                self.usage["calls"] += 1
                self.usage["prompt_tokens"] += u.get("prompt_tokens", len(system + user) // 4)
                self.usage["completion_tokens"] += u.get("completion_tokens", len(msg) // 4)
                if path:
                    with open(path, "w") as fh: json.dump(data, fh)
                return data
            except (urllib.error.URLError, LLMError, json.JSONDecodeError, KeyError) as e:
                last = e
                code = getattr(e, "code", 0)
                time.sleep(min(20, 1.5 ** attempt * (4 if code == 429 else 1)))
        raise LLMError(f"LLM call failed after {self.max_retries} tries: {last}")


def prompt_key(system, user):
    return hashlib.sha256(json.dumps([system, user]).encode()).hexdigest()[:24]


class ReplayLLM:
    """Plays back answers produced elsewhere (any model, any tool) for requests exported by `run.py --llm-export`.
    Keyed by the prompt text, so answers can never be attached to the wrong promo. Lets an editor use ANY model with no API plumbing."""
    def __init__(self, path):
        self.table = {}
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    d = json.loads(ln); self.table[d["key"]] = d["response"]
        meta = os.path.splitext(path)[0] + ".meta.json"
        self.meta = json.load(open(meta)) if os.path.exists(meta) else {}
        self.model = self.meta.get("model", "replayed")
        self.provider = self.meta.get("provider", "offline batch")
        self.usage = {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0, "missing": 0}

    def chat_json(self, system, user, required=()):
        k = prompt_key(system, user)
        if k not in self.table:
            self.usage["missing"] += 1; raise LLMError("no recorded answer for this prompt")
        d = self.table[k]; self.usage["cached"] += 1
        miss = [x for x in required if x not in d]
        if miss: raise LLMError(f"recorded answer missing keys {miss}")
        return d
