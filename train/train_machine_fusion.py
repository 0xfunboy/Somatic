#!/usr/bin/env python3
"""
Distill the analytic machine-fusion path into a learned TorchScript module.

The resulting model maps a 128D machine-state vector to a 4096D latent delta
that can be added to the somatic projector output at runtime.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


MACHINE_VECTOR_DIM = 128
LLM_EMB_DIM = 4096


class MachineFusionMLP(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(MACHINE_VECTOR_DIM, 256),
            nn.GELU(),
            nn.Linear(256, 512),
            nn.GELU(),
            nn.Linear(512, LLM_EMB_DIM),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def analytic_delta(machine_vectors: torch.Tensor) -> torch.Tensor:
    gain = 0.18
    batch, dim = machine_vectors.shape
    assert dim == MACHINE_VECTOR_DIM
    positions = torch.arange(LLM_EMB_DIM, device=machine_vectors.device, dtype=machine_vectors.dtype)
    mv = machine_vectors[:, positions.long() % MACHINE_VECTOR_DIM]
    harmonic = (
        0.62 * mv
        + 0.23 * torch.sin(mv * 1.7 + positions * 0.013)
        + 0.15 * torch.cos(positions * 0.021)
    )
    return gain * harmonic


def build_dataset(samples: int, scale: float, seed: int) -> tuple[torch.Tensor, torch.Tensor]:
    g = torch.Generator().manual_seed(seed)
    machine = torch.randn(samples, MACHINE_VECTOR_DIM, generator=g) * scale
    target = analytic_delta(machine)
    return machine, target


def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    machine, target = build_dataset(args.samples, args.scale, args.seed)
    dataset = TensorDataset(machine, target)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    model = MachineFusionMLP().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    criterion = nn.MSELoss()

    for epoch in range(1, args.epochs + 1):
        total = 0.0
        count = 0
        model.train()
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total += float(loss.item()) * len(xb)
            count += len(xb)
        avg_loss = total / max(count, 1)
        print(f"epoch={epoch:02d} loss={avg_loss:.8f}", flush=True)

    model.eval()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scripted = torch.jit.script(model.cpu())
    scripted.save(str(out_path))
    print(f"saved={out_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a learned machine-fusion TorchScript module")
    parser.add_argument("--output", default="weights/machine_fusion.pt")
    parser.add_argument("--samples", type=int, default=1536)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--scale", type=float, default=1.4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
