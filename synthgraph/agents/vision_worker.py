#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synthgraph/agents/vision_worker.py — SynthGraph V4.10

Worker vision JETABLE (exception d'architecture validée par Terry 2026-07-13).

Pourquoi un sous-processus : un crash NATIF du modèle vision (access violation
constatée avec le mmproj PaliGemma legacy) corrompt le contexte CUDA de tout le
process → 3 papiers d'un batch perdus en cascade. Ici, le crash ne tue que ce
worker ; l'OS récupère sa VRAM par construction ; le pipeline parent continue.

Contrat :
    argv[1] = chemin d'un job JSON {"model_path", "mmproj_path",
                                    "queries": [{"image": path, "question": str}]}
    stdout  = UNE ligne JSON finale {"answers": [str|null, ...]} ou {"error": str}
    stderr  = logs libres. Codes retour : 0 ok, 2 échec de chargement.

Ce worker vit le temps d'un lot de questions puis meurt. Ce n'est PAS un serveur
(la contrainte « pas de subprocess pour le cycle de vie LLM » vise les serveurs
persistants ; ceci est de l'isolation de crash, one-shot).
"""

import base64
import json
import sys
from pathlib import Path


def log(msg: str):
    print(f"[vision-worker] {msg}", file=sys.stderr, flush=True)


def main() -> int:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    model_path = job["model_path"]
    mmproj_path = job["mmproj_path"]
    queries = job.get("queries", [])

    from llama_cpp import Llama
    from llama_cpp import llama_chat_format as fmt

    if "qwen2.5-vl" in Path(model_path).name.lower():
        handler_names = ("Qwen25VLChatHandler", "MTMDChatHandler")
    else:
        handler_names = ("Llava15ChatHandler", "MTMDChatHandler")

    llm, errors = None, []
    for hn in handler_names:
        try:
            handler = getattr(fmt, hn)(clip_model_path=mmproj_path, verbose=False)
            llm = Llama(model_path=model_path, chat_handler=handler,
                        n_ctx=4096, n_gpu_layers=-1, verbose=False)  # [V4.19.3] 2048 → 4096 : 'Prompt exceeds n_ctx: 2699 > 2048' constaté au bench (prompts image+question longs), 100% d'échecs
            log(f"chargé via {hn}")
            break
        except Exception as e:
            errors.append(f"{hn}: {type(e).__name__}: {str(e)[:100]}")
            llm = None
    if llm is None:
        print(json.dumps({"error": f"load failed: {errors}"}, ensure_ascii=False), flush=True)
        return 2

    answers = []
    for q in queries:
        try:
            p = Path(q["image"])
            ext = p.suffix.lstrip(".").lower() or "png"
            ext = "jpeg" if ext == "jpg" else ext
            uri = f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()
            resp = llm.create_chat_completion(
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": uri}},
                    {"type": "text",
                     "text": (q["question"] + "\nAnswer with ONLY the value and unit "
                              "(e.g. '900 C' or '24 h'). If the image does not show "
                              "this information, answer exactly: not shown")},
                ]}],
                max_tokens=64, temperature=0.0,
            )
            ans = (resp["choices"][0]["message"]["content"] or "").strip()
            log(f"{p.name} → {ans[:60]!r}")
            answers.append(ans)
        except Exception as e:
            log(f"échec requête: {type(e).__name__}: {str(e)[:100]}")
            answers.append(None)

    print(json.dumps({"answers": answers}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
