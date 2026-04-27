from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .base import SensorProvider, clamp, normalize_snapshot, read_number, read_text, rounded
from .nvidia import NvidiaSMIProvider

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


class LinuxSystemProvider(SensorProvider):
    name = "linux"
    is_real = True

    def __init__(self):
        enable_nvidia = os.getenv("SOMA_ENABLE_NVIDIA", "1").strip().lower() not in {"0", "false", "no", "off"}
        self.nvidia = NvidiaSMIProvider() if enable_nvidia else None
        self.last_rapl_energy_uj: float | None = None
        self.last_rapl_at: float | None = None
        self.last_net_sent_bytes: float | None = None
        self.last_net_recv_bytes: float | None = None
        self.last_net_at: float | None = None
        self.last_disk_read_bytes: float | None = None
        self.last_disk_write_bytes: float | None = None
        self.last_disk_busy_time_ms: float | None = None
        self.last_disk_at: float | None = None

    def read(self) -> dict[str, object]:
        now = time.monotonic()
        hwmon = self._read_hwmon()
        thermal = self._read_thermal()
        power_supply = self._read_power_supply()
        cpu_power_w = self._read_rapl_power(now)
        nvidia = self.nvidia.read() if self.nvidia is not None else {
            "gpu_temp": None,
            "gpu_power_w": None,
            "gpu_util_percent": None,
            "gpu_memory_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
        }
        system_stats = self._read_psutil()

        cpu_temp = self._choose_cpu_temp(hwmon, thermal, system_stats)
        gpu_temp = nvidia["gpu_temp"]
        disk_temp = self._choose_storage_temp(hwmon)
        fan_rpm = self._choose_fan_rpm(hwmon, system_stats)
        battery_percent = power_supply["battery_percent"]
        voltage = power_supply["voltage_v"] or self._choose_voltage(hwmon)
        cpu_percent = system_stats["cpu_percent"]
        memory_percent = system_stats["memory_percent"]
        gpu_power_w = nvidia["gpu_power_w"]
        total_power_w = sum(
            value for value in (cpu_power_w, gpu_power_w, power_supply["power_w"]) if value is not None
        ) or None

        current_ma = power_supply["current_ma"]
        if current_ma is None and total_power_w is not None and voltage not in (None, 0):
            current_ma = (total_power_w / voltage) * 1000.0

        temp_si = cpu_temp or self._fallback_temp(hwmon, thermal) or 45.0
        temp_ml = gpu_temp or self._secondary_temp(hwmon, thermal) or max(32.0, temp_si - 4.0)
        temp_mr = self._tertiary_temp(hwmon, thermal) or gpu_temp or max(32.0, temp_si - 2.0)

        quality_inputs = (
            cpu_percent,
            memory_percent,
            cpu_temp,
            cpu_power_w,
            gpu_temp,
            gpu_power_w,
            nvidia["gpu_util_percent"],
            nvidia["gpu_memory_percent"],
            battery_percent,
            power_supply["ac_online"],
            fan_rpm,
            voltage,
            system_stats["disk_used_percent"],
            system_stats["disk_read_mb_s"],
            system_stats["disk_write_mb_s"],
            system_stats["net_up_mbps"],
            system_stats["net_down_mbps"],
            disk_temp,
        )
        real_fields = sum(value is not None for value in quality_inputs)
        source_quality = real_fields / len(quality_inputs)

        def rounded_list(values, digits: int = 2):
            if not values:
                return None
            return [round(float(value), digits) for value in values]

        snapshot = {
            "core": {
                "voltage": rounded(voltage or 12.0, 3),
                "current_ma": rounded(current_ma or 250.0, 2),
                "temp_si": rounded(temp_si, 3),
                "temp_ml": rounded(temp_ml, 3),
                "temp_mr": rounded(temp_mr, 3),
                "ax": 0.0,
                "ay": 0.0,
                "az": -9.81,
                "gx": 0.0,
                "gy": 0.0,
                "gz": 0.0,
            },
            "system": {
                "cpu_percent": rounded(cpu_percent, 2),
                "cpu_count_logical": system_stats["cpu_count_logical"],
                "cpu_count_physical": system_stats["cpu_count_physical"],
                "cpu_freq_mhz": rounded(system_stats["cpu_freq_mhz"], 2),
                "cpu_per_core_percent": rounded_list(system_stats["cpu_per_core_percent"], 2),
                "memory_percent": rounded(memory_percent, 2),
                "memory_used_gb": rounded(system_stats["memory_used_gb"], 3),
                "memory_total_gb": rounded(system_stats["memory_total_gb"], 3),
                "memory_available_gb": rounded(system_stats["memory_available_gb"], 3),
                "swap_percent": rounded(system_stats["swap_percent"], 2),
                "swap_used_gb": rounded(system_stats["swap_used_gb"], 3),
                "swap_total_gb": rounded(system_stats["swap_total_gb"], 3),
                "cpu_temp": rounded(cpu_temp, 2),
                "cpu_temp_sensors_c": rounded_list(system_stats["cpu_temp_sensors_c"], 2),
                "cpu_power_w": rounded(cpu_power_w, 2),
                "gpu_temp": rounded(gpu_temp, 2),
                "gpu_power_w": rounded(gpu_power_w, 2),
                "gpu_memory_used_mb": rounded(nvidia["gpu_memory_used_mb"], 2),
                "gpu_memory_total_mb": rounded(nvidia["gpu_memory_total_mb"], 2),
                "battery_percent": rounded(battery_percent, 2),
                "fan_rpm": rounded(fan_rpm, 1),
                "fan_sensors_rpm": rounded_list(system_stats["fan_sensors_rpm"], 1),
                "source_quality": source_quality,
                "gpu_util_percent": rounded(nvidia["gpu_util_percent"], 2),
                "gpu_memory_percent": rounded(nvidia["gpu_memory_percent"], 2),
                "ac_online": power_supply["ac_online"],
                "battery_plugged": power_supply["battery_plugged"],
                "load_1": rounded(system_stats["load_1"], 2),
                "load_5": rounded(system_stats["load_5"], 2),
                "load_15": rounded(system_stats["load_15"], 2),
                "net_mbps": rounded(system_stats["net_mbps"], 3),
                "net_up_mbps": rounded(system_stats["net_up_mbps"], 3),
                "net_down_mbps": rounded(system_stats["net_down_mbps"], 3),
                "disk_busy_percent": rounded(system_stats["disk_busy_percent"], 2),
                "disk_used_percent": rounded(system_stats["disk_used_percent"], 2),
                "disk_total_gb": rounded(system_stats["disk_total_gb"], 3),
                "disk_used_gb": rounded(system_stats["disk_used_gb"], 3),
                "disk_free_gb": rounded(system_stats["disk_free_gb"], 3),
                "disk_read_mb_s": rounded(system_stats["disk_read_mb_s"], 3),
                "disk_write_mb_s": rounded(system_stats["disk_write_mb_s"], 3),
                "disk_temp": rounded(disk_temp, 2),
                "thermal_sensors_c": rounded_list(system_stats["thermal_sensors_c"], 2),
            },
            "raw": {
                "hwmon_temp_count": len(hwmon["temps"]),
                "hwmon_fan_count": len(hwmon["fans"]),
                "hwmon_voltage_count": len(hwmon["voltages"]),
                "thermal_zone_count": len(thermal),
            },
        }

        # Merge auto-discovered fields for any system keys still None.
        try:
            from sensor_providers.discovered import read_discovered_fields  # type: ignore[import]
            discovered = read_discovered_fields()
            for key, value in discovered.items():
                if snapshot["system"].get(key) is None and value is not None:
                    try:
                        snapshot["system"][key] = rounded(float(value), 2)
                    except (TypeError, ValueError):
                        snapshot["system"][key] = value
        except ImportError:
            pass  # discovered.py not yet generated

        return normalize_snapshot(
            snapshot,
            provider=self.name,
            is_real=self.is_real,
        )

    def _read_hwmon(self) -> dict[str, list[dict[str, float | str | None]]]:
        result = {"temps": [], "fans": [], "voltages": []}
        base = Path("/sys/class/hwmon")
        if not base.exists():
            return result

        for hwmon_dir in base.glob("hwmon*"):
            chip_name = read_text(hwmon_dir / "name")
            for temp_path in hwmon_dir.glob("temp*_input"):
                label = read_text(temp_path.with_name(temp_path.name.replace("_input", "_label"))) or chip_name
                value = read_number(temp_path, scale=1000.0)
                if value is not None:
                    result["temps"].append({"label": label, "value": value})
            for fan_path in hwmon_dir.glob("fan*_input"):
                label = read_text(fan_path.with_name(fan_path.name.replace("_input", "_label"))) or chip_name
                value = read_number(fan_path, scale=1.0)
                if value is not None:
                    result["fans"].append({"label": label, "value": value})
            for volt_path in hwmon_dir.glob("in*_input"):
                label = read_text(volt_path.with_name(volt_path.name.replace("_input", "_label"))) or chip_name
                value = read_number(volt_path, scale=1000.0)
                if value is not None:
                    result["voltages"].append({"label": label, "value": value})
        return result

    def _read_thermal(self) -> list[dict[str, float | str | None]]:
        zones = []
        base = Path("/sys/class/thermal")
        if not base.exists():
            return zones

        for zone in base.glob("thermal_zone*"):
            value = read_number(zone / "temp", scale=1000.0)
            if value is None:
                continue
            label = read_text(zone / "type") or zone.name
            zones.append({"label": label, "value": value})
        return zones

    def _read_power_supply(self) -> dict[str, float | bool | None]:
        result = {
            "battery_percent": None,
            "voltage_v": None,
            "current_ma": None,
            "power_w": None,
            "ac_online": None,
            "battery_plugged": None,
        }
        base = Path("/sys/class/power_supply")
        if not base.exists():
            return result

        for entry in base.iterdir():
            ptype = (read_text(entry / "type") or "").lower()
            if ptype == "battery":
                result["battery_percent"] = read_number(entry / "capacity", scale=1.0)
                result["voltage_v"] = read_number(entry / "voltage_now", scale=1_000_000.0) or read_number(
                    entry / "voltage_avg", scale=1_000_000.0
                )
                current_a = read_number(entry / "current_now", scale=1_000_000.0)
                if current_a is not None:
                    result["current_ma"] = current_a * 1000.0
                power_w = read_number(entry / "power_now", scale=1_000_000.0)
                if power_w is not None:
                    result["power_w"] = power_w
                status = (read_text(entry / "status") or "").lower()
                if status:
                    result["battery_plugged"] = status in {"charging", "full"}
            elif ptype in {"mains", "ac", "usb"}:
                online = read_number(entry / "online", scale=1.0)
                if online is not None:
                    result["ac_online"] = bool(int(online))
        return result

    def _read_rapl_power(self, now: float) -> float | None:
        base = Path("/sys/class/powercap")
        if not base.exists():
            return None

        total_uj = 0.0
        found = False
        for domain in base.glob("intel-rapl:*"):
            if domain.name.count(":") != 1:
                continue
            energy_uj = read_number(domain / "energy_uj", scale=1.0)
            if energy_uj is None:
                continue
            total_uj += energy_uj
            found = True

        if not found:
            return None

        power_w = None
        if self.last_rapl_energy_uj is not None and self.last_rapl_at is not None:
            dt = now - self.last_rapl_at
            if dt > 0:
                delta_uj = total_uj - self.last_rapl_energy_uj
                if delta_uj < 0:
                    delta_uj = total_uj
                power_w = (delta_uj / 1_000_000.0) / dt

        self.last_rapl_energy_uj = total_uj
        self.last_rapl_at = now
        return power_w

    def _read_psutil(self) -> dict[str, float | bool | None]:
        stats = {
            "cpu_percent": None,
            "cpu_count_logical": None,
            "cpu_count_physical": None,
            "cpu_freq_mhz": None,
            "cpu_per_core_percent": None,
            "memory_percent": None,
            "memory_used_gb": None,
            "memory_total_gb": None,
            "memory_available_gb": None,
            "swap_percent": None,
            "swap_used_gb": None,
            "swap_total_gb": None,
            "load_1": None,
            "load_5": None,
            "load_15": None,
            "net_mbps": None,
            "net_up_mbps": None,
            "net_down_mbps": None,
            "disk_busy_percent": None,
            "disk_used_percent": None,
            "disk_total_gb": None,
            "disk_used_gb": None,
            "disk_free_gb": None,
            "disk_read_mb_s": None,
            "disk_write_mb_s": None,
            "cpu_temp": None,
            "cpu_temp_sensors_c": None,
            "fan_rpm": None,
            "fan_sensors_rpm": None,
            "battery_percent": None,
            "battery_plugged": None,
            "thermal_sensors_c": None,
        }

        if psutil is None:
            stats["cpu_count_logical"] = os.cpu_count()
            stats["cpu_freq_mhz"] = self._read_proc_cpu_freq_mhz()
            meminfo = self._read_proc_meminfo()
            if meminfo:
                total_kb = meminfo.get("MemTotal")
                available_kb = meminfo.get("MemAvailable")
                swap_total_kb = meminfo.get("SwapTotal")
                swap_free_kb = meminfo.get("SwapFree")
                if total_kb and available_kb is not None:
                    used_kb = max(0.0, total_kb - available_kb)
                    stats["memory_total_gb"] = total_kb / (1024**2)
                    stats["memory_available_gb"] = available_kb / (1024**2)
                    stats["memory_used_gb"] = used_kb / (1024**2)
                    stats["memory_percent"] = (used_kb / total_kb) * 100.0
                if swap_total_kb:
                    swap_used_kb = max(0.0, swap_total_kb - float(swap_free_kb or 0.0))
                    stats["swap_total_gb"] = swap_total_kb / (1024**2)
                    stats["swap_used_gb"] = swap_used_kb / (1024**2)
                    stats["swap_percent"] = (swap_used_kb / swap_total_kb) * 100.0 if swap_total_kb else 0.0
            try:
                disk = shutil.disk_usage("/")
                stats["disk_total_gb"] = disk.total / (1024**3)
                stats["disk_used_gb"] = disk.used / (1024**3)
                stats["disk_free_gb"] = disk.free / (1024**3)
                stats["disk_used_percent"] = (disk.used / disk.total) * 100.0 if disk.total else None
            except OSError:
                pass
            self._read_proc_net(stats)
            try:
                load_1, load_5, load_15 = os.getloadavg()
                stats["load_1"] = load_1
                stats["load_5"] = load_5
                stats["load_15"] = load_15
            except OSError:
                pass
            return stats

        stats["cpu_percent"] = psutil.cpu_percent(interval=None)
        stats["cpu_count_logical"] = psutil.cpu_count(logical=True)
        stats["cpu_count_physical"] = psutil.cpu_count(logical=False)
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            stats["cpu_freq_mhz"] = cpu_freq.current
        try:
            stats["cpu_per_core_percent"] = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:  # pragma: no cover - psutil/platform quirks
            pass

        memory = psutil.virtual_memory()
        stats["memory_percent"] = memory.percent
        stats["memory_used_gb"] = memory.used / (1024**3)
        stats["memory_total_gb"] = memory.total / (1024**3)
        stats["memory_available_gb"] = memory.available / (1024**3)

        try:
            swap = psutil.swap_memory()
            stats["swap_percent"] = swap.percent
            stats["swap_used_gb"] = swap.used / (1024**3)
            stats["swap_total_gb"] = swap.total / (1024**3)
        except Exception:  # pragma: no cover
            pass

        try:
            load_1, load_5, load_15 = os.getloadavg()
            stats["load_1"] = load_1
            stats["load_5"] = load_5
            stats["load_15"] = load_15
        except OSError:
            pass

        try:
            net_io = psutil.net_io_counters()
            now = time.monotonic()
            sent_bytes = float(net_io.bytes_sent)
            recv_bytes = float(net_io.bytes_recv)
            if (
                self.last_net_sent_bytes is not None
                and self.last_net_recv_bytes is not None
                and self.last_net_at is not None
            ):
                dt = now - self.last_net_at
                if dt > 0:
                    sent_mbps = ((sent_bytes - self.last_net_sent_bytes) * 8.0) / dt / 1_000_000.0
                    recv_mbps = ((recv_bytes - self.last_net_recv_bytes) * 8.0) / dt / 1_000_000.0
                    stats["net_up_mbps"] = max(0.0, sent_mbps)
                    stats["net_down_mbps"] = max(0.0, recv_mbps)
                    stats["net_mbps"] = max(0.0, sent_mbps + recv_mbps)
            self.last_net_sent_bytes = sent_bytes
            self.last_net_recv_bytes = recv_bytes
            self.last_net_at = now
        except Exception:  # pragma: no cover - psutil/platform quirks
            pass

        try:
            usage = psutil.disk_usage("/")
            stats["disk_used_percent"] = usage.percent
            stats["disk_total_gb"] = usage.total / (1024**3)
            stats["disk_used_gb"] = usage.used / (1024**3)
            stats["disk_free_gb"] = usage.free / (1024**3)
        except Exception:  # pragma: no cover
            pass

        try:
            disk = psutil.disk_io_counters()
            now = time.monotonic()
            if disk:
                read_bytes = float(getattr(disk, "read_bytes", 0.0))
                write_bytes = float(getattr(disk, "write_bytes", 0.0))
                busy_time_ms = float(getattr(disk, "busy_time", 0.0) or 0.0)
                if (
                    self.last_disk_read_bytes is not None
                    and self.last_disk_write_bytes is not None
                    and self.last_disk_busy_time_ms is not None
                    and self.last_disk_at is not None
                ):
                    dt = now - self.last_disk_at
                    if dt > 0:
                        stats["disk_read_mb_s"] = max(0.0, (read_bytes - self.last_disk_read_bytes) / dt / 1_000_000.0)
                        stats["disk_write_mb_s"] = max(0.0, (write_bytes - self.last_disk_write_bytes) / dt / 1_000_000.0)
                        busy_delta = busy_time_ms - self.last_disk_busy_time_ms
                        if busy_delta < 0:
                            busy_delta = 0.0
                        stats["disk_busy_percent"] = clamp((busy_delta / (dt * 1000.0)) * 100.0, 0.0, 100.0)
                self.last_disk_read_bytes = read_bytes
                self.last_disk_write_bytes = write_bytes
                self.last_disk_busy_time_ms = busy_time_ms
                self.last_disk_at = now
        except Exception:  # pragma: no cover
            pass

        try:
            temps = psutil.sensors_temperatures(fahrenheit=False)
        except Exception:  # pragma: no cover
            temps = {}

        cpu_temp = None
        for entries in temps.values():
            for entry in entries:
                label = (entry.label or "").lower()
                if any(token in label for token in ("package", "cpu", "tctl", "tdie", "core")):
                    cpu_temp = entry.current
                    break
            if cpu_temp is not None:
                break
        if cpu_temp is None:
            for entries in temps.values():
                if entries:
                    cpu_temp = entries[0].current
                    break
        stats["cpu_temp"] = cpu_temp
        flattened_temps = []
        for entries in temps.values():
            for entry in entries:
                if entry.current is not None:
                    flattened_temps.append(float(entry.current))
        if flattened_temps:
            stats["cpu_temp_sensors_c"] = flattened_temps[:16]
            stats["thermal_sensors_c"] = flattened_temps[:16]

        try:
            fans = psutil.sensors_fans()
        except Exception:  # pragma: no cover
            fans = {}
        fan_values = []
        for entries in fans.values():
            for entry in entries:
                if entry.current:
                    fan_values.append(float(entry.current))
        if fan_values:
            stats["fan_rpm"] = max(fan_values)
            stats["fan_sensors_rpm"] = fan_values[:16]

        try:
            battery = psutil.sensors_battery()
        except Exception:  # pragma: no cover
            battery = None
        if battery:
            stats["battery_percent"] = battery.percent
            stats["battery_plugged"] = battery.power_plugged

        return stats

    def _choose_cpu_temp(self, hwmon, thermal, system_stats) -> float | None:
        preferred = ("package", "cpu", "core", "tctl", "tdie", "soc")
        temperatures = hwmon["temps"] + thermal
        ranked = []
        for item in temperatures:
            label = str(item.get("label") or "").lower()
            value = item.get("value")
            if value is None:
                continue
            score = 0
            if any(token in label for token in preferred):
                score += 10
            score += min(float(value), 120.0) / 100.0
            ranked.append((score, float(value)))
        if ranked:
            ranked.sort(reverse=True)
            return ranked[0][1]
        return system_stats["cpu_temp"]

    def _fallback_temp(self, hwmon, thermal) -> float | None:
        values = [float(item["value"]) for item in hwmon["temps"] + thermal if item.get("value") is not None]
        return max(values) if values else None

    def _secondary_temp(self, hwmon, thermal) -> float | None:
        values = sorted(
            [float(item["value"]) for item in hwmon["temps"] + thermal if item.get("value") is not None],
            reverse=True,
        )
        return values[1] if len(values) > 1 else None

    def _tertiary_temp(self, hwmon, thermal) -> float | None:
        values = sorted(
            [float(item["value"]) for item in hwmon["temps"] + thermal if item.get("value") is not None],
            reverse=True,
        )
        return values[2] if len(values) > 2 else None

    def _choose_fan_rpm(self, hwmon, system_stats) -> float | None:
        values = [float(item["value"]) for item in hwmon["fans"] if item.get("value") is not None]
        if values:
            return max(values)
        return system_stats["fan_rpm"]

    def _choose_voltage(self, hwmon) -> float | None:
        preferred = ("vbat", "bat", "in0", "vin")
        ranked = []
        for item in hwmon["voltages"]:
            label = str(item.get("label") or "").lower()
            value = item.get("value")
            if value is None:
                continue
            score = 0
            if any(token in label for token in preferred):
                score += 10
            score -= abs(float(value) - 12.0)
            ranked.append((score, float(value)))
        if not ranked:
            return None
        ranked.sort(reverse=True)
        return ranked[0][1]

    def _choose_storage_temp(self, hwmon) -> float | None:
        preferred = ("nvme", "ssd", "composite", "drive", "pch")
        ranked = []
        for item in hwmon["temps"]:
            label = str(item.get("label") or "").lower()
            value = item.get("value")
            if value is None:
                continue
            score = 0
            if any(token in label for token in preferred):
                score += 10
            ranked.append((score, float(value)))
        if not ranked:
            return None
        ranked.sort(reverse=True)
        return ranked[0][1]

    def _read_proc_meminfo(self) -> dict[str, float]:
        path = Path("/proc/meminfo")
        if not path.exists():
            return {}
        result: dict[str, float] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, raw_value = line.split(":", 1)
            parts = raw_value.strip().split()
            if not parts:
                continue
            try:
                result[key] = float(parts[0])
            except ValueError:
                continue
        return result

    def _read_proc_cpu_freq_mhz(self) -> float | None:
        cpufreq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
        if cpufreq_path.exists():
            value = read_number(cpufreq_path, scale=1000.0)
            if value is not None:
                return value
        cpuinfo = Path("/proc/cpuinfo")
        if not cpuinfo.exists():
            return None
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("cpu mhz") and ":" in line:
                try:
                    return float(line.split(":", 1)[1].strip())
                except ValueError:
                    return None
        return None

    def _read_proc_net(self, stats: dict[str, float | bool | None]) -> None:
        path = Path("/proc/net/dev")
        if not path.exists():
            return
        recv_bytes = 0.0
        sent_bytes = 0.0
        for line in path.read_text(encoding="utf-8").splitlines()[2:]:
            if ":" not in line:
                continue
            iface, values = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            parts = values.split()
            if len(parts) < 16:
                continue
            try:
                recv_bytes += float(parts[0])
                sent_bytes += float(parts[8])
            except ValueError:
                continue
        now = time.monotonic()
        if (
            self.last_net_sent_bytes is not None
            and self.last_net_recv_bytes is not None
            and self.last_net_at is not None
        ):
            dt = now - self.last_net_at
            if dt > 0:
                sent_mbps = ((sent_bytes - self.last_net_sent_bytes) * 8.0) / dt / 1_000_000.0
                recv_mbps = ((recv_bytes - self.last_net_recv_bytes) * 8.0) / dt / 1_000_000.0
                stats["net_up_mbps"] = max(0.0, sent_mbps)
                stats["net_down_mbps"] = max(0.0, recv_mbps)
                stats["net_mbps"] = max(0.0, sent_mbps + recv_mbps)
        self.last_net_sent_bytes = sent_bytes
        self.last_net_recv_bytes = recv_bytes
        self.last_net_at = now
