#!/bin/sh
# Rileva l'hardware dell'host e lo scrive in $RAG_DATA_DIR/config/host.json.
# Va eseguito sull'host (non nel container): il container vede solo la VM di Colima.
# Uso: scripts/host-probe.sh [cartella-dati]   (default: ~/haiku-rag-data)
set -e

DATA_DIR="${1:-${RAG_DATA_DIR:-$HOME/haiku-rag-data}}"
OUT="$DATA_DIR/config/host.json"
mkdir -p "$DATA_DIR/config"

# Memoria che la GPU Metal può usare davvero (la stessa che usa Ollama per decidere l'offload)
METAL_BYTES=""
if [ "$(uname -s)" = "Darwin" ] && command -v swift >/dev/null 2>&1; then
    METAL_BYTES=$(echo 'import Metal; print(MTLCreateSystemDefaultDevice()!.recommendedMaxWorkingSetSize)' \
        | swift - 2>/dev/null || true)
fi

METAL_BYTES="$METAL_BYTES" python3 - "$OUT" <<'EOF'
import json, os, platform, shutil, subprocess, sys
from datetime import datetime, timezone

def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""

GIB = 2**30
info = {
    "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "os": platform.system(),
    "os_version": platform.release(),
    "arch": platform.machine(),
}

if info["os"] == "Darwin":
    hw = json.loads(run("system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "-json") or "{}")
    h = (hw.get("SPHardwareDataType") or [{}])[0]
    g = (hw.get("SPDisplaysDataType") or [{}])[0]
    ram = int(run("sysctl", "-n", "hw.memsize") or 0)
    wired_mb = int(run("sysctl", "-n", "iogpu.wired_limit_mb") or 0)
    metal = int(os.environ.get("METAL_BYTES") or 0)
    if metal:
        gpu_mem, source = metal, "metal.recommendedMaxWorkingSetSize"
    elif wired_mb:
        gpu_mem, source = wired_mb * 2**20, "sysctl iogpu.wired_limit_mb"
    else:
        gpu_mem, source = int(ram * 0.75), "stima 75% RAM"
    info.update({
        "chip": h.get("chip_type") or h.get("cpu_type"),
        "model": h.get("machine_model"),
        "cpu_performance_cores": int(run("sysctl", "-n", "hw.perflevel0.physicalcpu") or 0),
        "cpu_efficiency_cores": int(run("sysctl", "-n", "hw.perflevel1.physicalcpu") or 0),
        "gpu": g.get("sppci_model"),
        "gpu_cores": int(g.get("sppci_cores") or 0),
        "unified_memory": True,
        "ram_gib": round(ram / GIB, 1),
        "gpu_memory_gib": round(gpu_mem / GIB, 2),
        "gpu_memory_source": source,
    })
else:
    meminfo = dict(l.split(":", 1) for l in open("/proc/meminfo"))
    ram = int(meminfo["MemTotal"].split()[0]) * 1024
    smi = run("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits")
    gpus = [l.split(", ") for l in smi.splitlines() if l]
    info.update({
        "chip": run("sh", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip(),
        "cpu_cores": os.cpu_count(),
        "gpu": ", ".join(g[0] for g in gpus) or None,
        "unified_memory": False,
        "ram_gib": round(ram / GIB, 1),
        "gpu_memory_gib": round(sum(int(g[1]) for g in gpus) / 1024, 2) if gpus else 0,
        "gpu_memory_source": "nvidia-smi" if gpus else "nessuna GPU: inferenza su CPU",
    })

info["disk_free_gib"] = round(shutil.disk_usage(os.path.expanduser("~")).free / GIB, 1)

with open(sys.argv[1], "w") as f:
    json.dump(info, f, indent=2)
print(json.dumps(info, indent=2))
EOF
echo "Scritto $OUT"
