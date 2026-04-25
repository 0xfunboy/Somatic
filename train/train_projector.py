"""
Contrastive training for SomaticProjector.

Goal: align the MLP's output (R^N_sensor → R^D_model) with the embedding space
of a frozen text encoder, so that a hardware state like {voltage=10.0V} maps to
the same region of R^D_model as "I feel weak, energy is draining."

Loss: InfoNCE (symmetric NT-Xent), same as CLIP.
The temperature τ is learned.

After training, export weights with:
    python train_projector.py --export weights/somatic_projector.pt
"""

import argparse
import math
import json
import random
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sentence_transformers import SentenceTransformer


# ---------------------------------------------------------------------------
# Dimensions — must match C++ constants in somatic_projector.h
# ---------------------------------------------------------------------------
SENSOR_DIM  = 11   # [voltage, current_ma, temp_si, temp_ml, temp_mr, ax, ay, az, gx, gy, gz]
HIDDEN_1    = 256
HIDDEN_2    = 1024
LLM_EMB_DIM = 4096  # LLaMA-3 8B/70B

# Use a smaller text encoder here because we only need a proxy embedding space
# for alignment. At inference the real LLM embedding lookup is used.
TEXT_ENCODER_MODEL = "all-mpnet-base-v2"  # 768-dim output


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class SensorTextPair:
    sensor: List[float]   # length SENSOR_DIM
    text:   str

# Canonical pairs: describe each extreme of every sensor in plain language.
# Expand this significantly for production — ideally with real telemetry logs
# and corresponding operator annotations or LLM-generated descriptions.
CANONICAL_PAIRS: List[Tuple[dict, str]] = [
    # voltage
    ({"voltage": 12.6, "current_ma": 1500}, "Battery fully charged, power reserve excellent."),
    ({"voltage": 11.8, "current_ma": 2000}, "Battery nominal, operating normally."),
    ({"voltage": 10.8, "current_ma": 2500}, "Battery low, performance may degrade soon."),
    ({"voltage": 10.2, "current_ma": 3000}, "Critical battery level, immediate recharge required, I feel extremely weak."),
    # temperature
    ({"temp_silicon": 30.0},  "System cool, thermal headroom ample."),
    ({"temp_silicon": 55.0},  "Normal operating temperature, stable."),
    ({"temp_silicon": 75.0},  "Running warm, elevated heat detected."),
    ({"temp_silicon": 85.0},  "Thermal warning, silicon approaching thermal limit, throttling imminent."),
    ({"temp_motor_l": 80.0},  "Left motor overheating, mechanical stress detected."),
    ({"temp_motor_r": 80.0},  "Right motor overheating, asymmetric thermal load."),
    # gravity / orientation
    ({"acc_z": -9.81, "acc_x": 0.0, "acc_y": 0.0},  "Standing upright, stable orientation, gravity nominal."),
    ({"acc_z":  0.0,  "acc_x": -9.81},               "Tilted 90 degrees to the left, balance compromised."),
    ({"acc_z":  9.81, "acc_x": 0.0},                  "Upside down, orientation inverted."),
    ({"acc_x": 5.0,  "acc_y": 3.0, "acc_z": -8.5},  "Moving dynamically, acceleration forces detected."),
    # gyroscope
    ({"gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0},  "Completely still, no rotational movement."),
    ({"gyro_z": 1.5},  "Rotating around vertical axis at moderate speed."),
    ({"gyro_x": 3.0},  "Pitching forward rapidly, possible fall in progress."),
    # current (load)
    ({"current_ma": 500},  "Minimal load, idling quietly."),
    ({"current_ma": 4000}, "Heavy load, operating near maximum current draw."),
    ({"current_ma": 6000}, "Overcurrent condition, abnormal power consumption."),
]

def state_from_dict(d: dict) -> List[float]:
    defaults = dict(
        voltage=11.8, current_ma=2000.0,
        temp_silicon=45.0, temp_motor_l=40.0, temp_motor_r=40.0,
        acc_x=0.0, acc_y=0.0, acc_z=-9.81,
        gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
    )
    defaults.update(d)
    return [
        defaults["voltage"], defaults["current_ma"],
        defaults["temp_silicon"], defaults["temp_motor_l"], defaults["temp_motor_r"],
        defaults["acc_x"], defaults["acc_y"], defaults["acc_z"],
        defaults["gyro_x"], defaults["gyro_y"], defaults["gyro_z"],
    ]

def augment_sensor(s: List[float], noise_pct: float = 0.03) -> List[float]:
    """Gaussian noise augmentation — expands the training set from canonical pairs."""
    return [v * (1.0 + random.gauss(0, noise_pct)) for v in s]


class SomaticDataset(Dataset):
    def __init__(self, pairs: List[SensorTextPair], n_augment: int = 20):
        self.items: List[SensorTextPair] = []
        for p in pairs:
            self.items.append(p)
            for _ in range(n_augment):
                self.items.append(SensorTextPair(
                    sensor=augment_sensor(p.sensor),
                    text=p.text,
                ))

    def __len__(self): return len(self.items)

    def __getitem__(self, idx) -> Tuple[torch.Tensor, str]:
        item = self.items[idx]
        return torch.tensor(item.sensor, dtype=torch.float32), item.text


# ---------------------------------------------------------------------------
# SomaticProjector (mirrors C++ struct — must stay in sync)
# ---------------------------------------------------------------------------

class SomaticProjector(nn.Module):
    def __init__(self, out_dim: int = LLM_EMB_DIM):
        super().__init__()
        self.fc1 = nn.Linear(SENSOR_DIM, HIDDEN_1)
        self.fc2 = nn.Linear(HIDDEN_1,   HIDDEN_2)
        self.fc3 = nn.Linear(HIDDEN_2,   out_dim)
        self.ln  = nn.LayerNorm(out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.gelu(self.fc1(x))
        x = F.gelu(self.fc2(x))
        return self.ln(self.fc3(x))


# ---------------------------------------------------------------------------
# Adapter: text encoder → LLM_EMB_DIM
# sentence-transformers emits 768-dim vectors; we project to LLM_EMB_DIM
# so InfoNCE is computed in the same space as the target LLM.
# ---------------------------------------------------------------------------

class TextAdapter(nn.Module):
    def __init__(self, in_dim: int, out_dim: int = LLM_EMB_DIM):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(in_dim, out_dim),
            nn.LayerNorm(out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)


# ---------------------------------------------------------------------------
# InfoNCE loss (symmetric, à la CLIP)
# ---------------------------------------------------------------------------

class InfoNCELoss(nn.Module):
    def __init__(self):
        super().__init__()
        # Learned temperature — initialise at log(1/0.07) ≈ 2.66
        self.log_temp = nn.Parameter(torch.tensor(math.log(1.0 / 0.07)))

    def forward(self, z_sensor: torch.Tensor, z_text: torch.Tensor) -> torch.Tensor:
        # L2-normalise both sides
        zs = F.normalize(z_sensor, dim=-1)
        zt = F.normalize(z_text,   dim=-1)

        temp = self.log_temp.exp().clamp(max=100.0)
        logits = zs @ zt.T * temp           # [B, B]
        labels = torch.arange(len(logits), device=logits.device)

        loss_s2t = F.cross_entropy(logits,   labels)
        loss_t2s = F.cross_entropy(logits.T, labels)
        return (loss_s2t + loss_t2s) / 2.0


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def collate_fn_indexed(batch):
    # Returns (sensor_tensor, index_in_dataset)
    sensors = torch.stack([b[0] for b in batch])
    idxs    = torch.tensor([b[1] for b in batch], dtype=torch.long)
    return sensors, idxs


class SomaticDatasetIndexed(Dataset):
    """Like SomaticDataset but __getitem__ returns (sensor, idx) for embedding lookup."""
    def __init__(self, pairs: List[SensorTextPair], n_augment: int = 20):
        self.items: List[SensorTextPair] = []
        for p in pairs:
            self.items.append(p)
            for _ in range(n_augment):
                self.items.append(SensorTextPair(
                    sensor=augment_sensor(p.sensor),
                    text=p.text,
                ))

    def __len__(self): return len(self.items)

    def __getitem__(self, idx) -> Tuple[torch.Tensor, int]:
        item = self.items[idx]
        return torch.tensor(item.sensor, dtype=torch.float32), idx

    def all_texts(self) -> List[str]:
        return [item.text for item in self.items]


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}", flush=True)

    # --- Text encoder (frozen) — run ONCE to pre-cache all embeddings ---
    print(f"Loading text encoder: {TEXT_ENCODER_MODEL}", flush=True)
    text_enc = SentenceTransformer(TEXT_ENCODER_MODEL, device="cpu")
    try:
        text_dim = text_enc.get_embedding_dimension()
    except AttributeError:
        text_dim = text_enc.get_sentence_embedding_dimension()
    print(f"Text encoder dim: {text_dim}", flush=True)

    # --- Dataset ---
    pairs = [SensorTextPair(sensor=state_from_dict(d), text=t)
             for d, t in CANONICAL_PAIRS]
    if args.extra_data and Path(args.extra_data).exists():
        with open(args.extra_data) as f:
            for line in f:
                row = json.loads(line)
                pairs.append(SensorTextPair(
                    sensor=state_from_dict(row["sensor"]),
                    text=row["text"],
                ))

    dataset = SomaticDatasetIndexed(pairs, n_augment=args.augment)
    print(f"Dataset: {len(dataset)} samples — pre-computing text embeddings...", flush=True)

    # Pre-compute ALL text embeddings once. On CPU this takes a few seconds total
    # instead of (n_batches × n_epochs) transformer forward passes.
    all_texts = dataset.all_texts()
    with torch.no_grad():
        raw_all = text_enc.encode(all_texts, batch_size=64, show_progress_bar=True,
                                  convert_to_numpy=True)
    text_emb_cache = torch.tensor(raw_all, dtype=torch.float32).to(device)
    del text_enc  # free RAM
    print(f"Text embedding cache: {text_emb_cache.shape}", flush=True)

    loader = DataLoader(dataset, batch_size=args.batch_size,
                        shuffle=True, collate_fn=collate_fn_indexed, drop_last=True)

    # --- Models ---
    projector    = SomaticProjector(out_dim=LLM_EMB_DIM).to(device)
    text_adapter = TextAdapter(text_dim, LLM_EMB_DIM).to(device)
    criterion    = InfoNCELoss().to(device)

    params = (list(projector.parameters()) +
              list(text_adapter.parameters()) +
              list(criterion.parameters()))
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_loss = float("inf")

    for epoch in range(1, args.epochs + 1):
        projector.train()
        text_adapter.train()
        epoch_loss = 0.0
        n_batches  = 0

        for sensors, idxs in loader:
            sensors = sensors.to(device)

            z_sensor = projector(sensors)

            # Look up pre-cached embeddings — O(1), no encoder inference
            raw_text_emb = text_emb_cache[idxs]
            z_text = text_adapter(raw_text_emb)

            loss = criterion(z_sensor, z_text)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches  += 1

        scheduler.step()
        avg = epoch_loss / n_batches
        temp_val = criterion.log_temp.exp().item()

        if epoch % 10 == 0 or epoch == 1:
            print(f"Epoch {epoch:4d}/{args.epochs}  loss={avg:.4f}  τ={temp_val:.3f}", flush=True)

        if avg < best_loss:
            best_loss = avg
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            # Save projector as TorchScript (for C++ inference)
            scripted = torch.jit.script(projector.cpu())
            scripted.save(str(out))
            projector.to(device)
            # Save TextAdapter state dict for eval
            torch.save(text_adapter.state_dict(),
                       str(out).replace(".pt", "_adapter.pth"))

    print(f"\nBest loss: {best_loss:.4f} — projector saved to {args.output}", flush=True)
    print("Load in C++ with: torch::jit::load(\"weights/somatic_projector.pt\")", flush=True)


# ---------------------------------------------------------------------------
# Cosine similarity evaluation (quick sanity check)
# ---------------------------------------------------------------------------

def evaluate(args):
    device = torch.device("cpu")
    text_enc = SentenceTransformer(TEXT_ENCODER_MODEL, device="cpu")
    try:
        text_dim = text_enc.get_embedding_dimension()
    except AttributeError:
        text_dim = text_enc.get_sentence_embedding_dimension()

    projector_jit = torch.jit.load(args.output, map_location=device)
    projector_jit.eval()

    adapter_path = args.output.replace(".pt", "_adapter.pth")
    adapter = TextAdapter(text_dim, LLM_EMB_DIM)
    adapter.load_state_dict(torch.load(adapter_path, map_location=device))
    adapter.eval()

    test_cases = [
        ({"voltage": 10.2},        "I am critically low on energy."),
        ({"temp_silicon": 85.0},   "I am overheating."),
        ({"acc_z": -9.81},         "Standing upright, stable."),
        ({"gyro_x": 3.0},          "Pitching forward, falling."),
    ]
    print("\n--- Cosine similarity in LLM latent space (higher = better alignment) ---")
    for state_dict, desc in test_cases:
        s = torch.tensor([state_from_dict(state_dict)], dtype=torch.float32)
        with torch.no_grad():
            zs = F.normalize(projector_jit(s), dim=-1)
            raw_t = torch.tensor(text_enc.encode([desc]), dtype=torch.float32)
            zt = F.normalize(adapter(raw_t), dim=-1)
        sim = (zs @ zt.T).item()
        print(f"  {desc[:50]:<50s}  sim={sim:+.4f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--epochs",     type=int,   default=200)
    p.add_argument("--batch-size", type=int,   default=32)
    p.add_argument("--lr",         type=float, default=3e-4)
    p.add_argument("--augment",    type=int,   default=50,
                   help="augmented copies per canonical pair")
    p.add_argument("--output",     default="../weights/somatic_projector.pt")
    p.add_argument("--extra-data", default=None,
                   help="path to JSONL file with {sensor: {...}, text: '...'} rows")
    p.add_argument("--eval-only",  action="store_true")
    args = p.parse_args()

    if args.eval_only:
        evaluate(args)
    else:
        train(args)
        evaluate(args)
