#pragma once
#include <cstdint>
#include <atomic>
#include <mutex>
#include <functional>

// Raw sensor state — all values in SI units where applicable.
// voltage: Volts, temp: Celsius, acc_*: m/s², gyro_*: rad/s, current_ma: milliamps
struct HardwareState {
    float voltage;
    float current_ma;
    float temp_silicon;
    float temp_motor_l;
    float temp_motor_r;
    float acc_x;
    float acc_y;
    float acc_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;

    static constexpr int DIM = 11;
    void to_array(float out[DIM]) const;
};

// Voltage threshold below which the hardware thread triggers a survival override
// independently of the LLM forward pass (hard-realtime gate).
static constexpr float CRITICAL_VOLTAGE_V  = 10.5f;
static constexpr float CRITICAL_TEMP_C     = 85.0f;

// Callback invoked from hardware thread when a critical condition fires.
// Must be async-signal-safe: no heap allocation, no locking.
using SurvivalCallback = std::function<void(const HardwareState&)>;

class HWInterface {
public:
    explicit HWInterface(SurvivalCallback cb = nullptr);
    ~HWInterface();

    // Starts the background sensor polling thread (100 Hz).
    void start();
    void stop();

    // Thread-safe snapshot of the latest sensor state.
    HardwareState snapshot() const;

    // Returns false if the I2C bus could not be opened (falls back to mock data).
    bool is_hardware_available() const { return hw_available_; }

private:
    void poll_loop();
    HardwareState read_sensors_i2c();
    HardwareState read_sensors_mock();

    mutable std::mutex mtx_;
    HardwareState current_{};
    std::atomic<bool> running_{false};
    std::atomic<bool> hw_available_{false};
    SurvivalCallback survival_cb_;

    // I2C file descriptors (Linux /dev/i2c-*)
    int fd_bms_  = -1;   // BMS (voltage/current)
    int fd_imu_  = -1;   // ICM-42688-P or MPU-9250
    int fd_thm_  = -1;   // Thermistor ADC (TMP117 or similar)
};
