#include "hw_interface.h"
#include <thread>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>

// Linux I2C
#ifdef __linux__
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
static constexpr const char* I2C_BUS = "/dev/i2c-1";
#endif

// BMS I2C address (example: Texas Instruments BQ34Z100)
static constexpr uint8_t BMS_ADDR = 0x55;
// IMU I2C address (ICM-42688-P default)
static constexpr uint8_t IMU_ADDR = 0x68;
// Thermistor ADC (TMP117)
static constexpr uint8_t THM_ADDR = 0x48;

static constexpr int POLL_INTERVAL_MS = 10; // 100 Hz

void HardwareState::to_array(float out[DIM]) const {
    out[0]  = voltage;
    out[1]  = current_ma;
    out[2]  = temp_silicon;
    out[3]  = temp_motor_l;
    out[4]  = temp_motor_r;
    out[5]  = acc_x;
    out[6]  = acc_y;
    out[7]  = acc_z;
    out[8]  = gyro_x;
    out[9]  = gyro_y;
    out[10] = gyro_z;
}

HWInterface::HWInterface(SurvivalCallback cb) : survival_cb_(std::move(cb)) {}

HWInterface::~HWInterface() { stop(); }

void HWInterface::start() {
    running_.store(true);
#ifdef __linux__
    fd_bms_ = open(I2C_BUS, O_RDWR);
    fd_imu_ = open(I2C_BUS, O_RDWR);
    fd_thm_ = open(I2C_BUS, O_RDWR);
    hw_available_.store(fd_bms_ >= 0 && fd_imu_ >= 0 && fd_thm_ >= 0);
#else
    hw_available_.store(false);
#endif
    if (!hw_available_) {
        fprintf(stderr, "[HW] I2C unavailable — running in mock mode\n");
    }
    std::thread(&HWInterface::poll_loop, this).detach();
}

void HWInterface::stop() {
    running_.store(false);
#ifdef __linux__
    if (fd_bms_ >= 0) { close(fd_bms_); fd_bms_ = -1; }
    if (fd_imu_ >= 0) { close(fd_imu_); fd_imu_ = -1; }
    if (fd_thm_ >= 0) { close(fd_thm_); fd_thm_ = -1; }
#endif
}

HardwareState HWInterface::snapshot() const {
    std::lock_guard<std::mutex> lk(mtx_);
    return current_;
}

void HWInterface::poll_loop() {
    while (running_.load()) {
        HardwareState s = hw_available_ ? read_sensors_i2c() : read_sensors_mock();

        // Hard-realtime survival gate — evaluated before acquiring the shared lock.
        bool critical = (s.voltage < CRITICAL_VOLTAGE_V) || (s.temp_silicon > CRITICAL_TEMP_C);
        if (critical && survival_cb_) {
            survival_cb_(s);  // must be lock-free and signal-safe
        }

        {
            std::lock_guard<std::mutex> lk(mtx_);
            current_ = s;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(POLL_INTERVAL_MS));
    }
}

// --- I2C reads (device-specific register maps) ---

#ifdef __linux__
static int16_t i2c_read_word(int fd, uint8_t dev_addr, uint8_t reg) {
    ioctl(fd, I2C_SLAVE, dev_addr);
    write(fd, &reg, 1);
    uint8_t buf[2] = {};
    read(fd, buf, 2);
    return static_cast<int16_t>((buf[0] << 8) | buf[1]);
}
#endif

HardwareState HWInterface::read_sensors_i2c() {
    HardwareState s{};
#ifdef __linux__
    // BQ34Z100: voltage at reg 0x08 (mV), current at reg 0x0A (mA signed)
    int16_t raw_v  = i2c_read_word(fd_bms_, BMS_ADDR, 0x08);
    int16_t raw_i  = i2c_read_word(fd_bms_, BMS_ADDR, 0x0A);
    s.voltage      = raw_v / 1000.0f;
    s.current_ma   = static_cast<float>(raw_i);

    // ICM-42688-P: accel at 0x1F, gyro at 0x25 (±16g, ±2000dps, 16-bit)
    constexpr float ACCEL_SCALE = 16.0f * 9.80665f / 32768.0f;
    constexpr float GYRO_SCALE  = 2000.0f * (3.14159265f / 180.0f) / 32768.0f;
    s.acc_x  = i2c_read_word(fd_imu_, IMU_ADDR, 0x1F) * ACCEL_SCALE;
    s.acc_y  = i2c_read_word(fd_imu_, IMU_ADDR, 0x21) * ACCEL_SCALE;
    s.acc_z  = i2c_read_word(fd_imu_, IMU_ADDR, 0x23) * ACCEL_SCALE;
    s.gyro_x = i2c_read_word(fd_imu_, IMU_ADDR, 0x25) * GYRO_SCALE;
    s.gyro_y = i2c_read_word(fd_imu_, IMU_ADDR, 0x27) * GYRO_SCALE;
    s.gyro_z = i2c_read_word(fd_imu_, IMU_ADDR, 0x29) * GYRO_SCALE;

    // TMP117: temp register 0x00, LSB = 0.0078125°C
    int16_t raw_t  = i2c_read_word(fd_thm_, THM_ADDR, 0x00);
    s.temp_silicon = raw_t * 0.0078125f;
    s.temp_motor_l = s.temp_silicon; // TODO: second sensor
    s.temp_motor_r = s.temp_silicon;
#endif
    return s;
}

// Deterministic mock: slow sinusoidal drift so the projector sees varying input.
HardwareState HWInterface::read_sensors_mock() {
    static double t = 0.0;
    t += POLL_INTERVAL_MS / 1000.0;

    HardwareState s{};
    s.voltage      = 11.8f + 0.4f * static_cast<float>(std::sin(t * 0.1));
    s.current_ma   = 2200.0f + 300.0f * static_cast<float>(std::sin(t * 0.3));
    s.temp_silicon = 45.0f + 5.0f * static_cast<float>(std::sin(t * 0.05));
    s.temp_motor_l = 38.0f + 3.0f * static_cast<float>(std::sin(t * 0.07));
    s.temp_motor_r = 38.0f + 3.0f * static_cast<float>(std::cos(t * 0.07));
    s.acc_x        = 0.1f * static_cast<float>(std::sin(t * 2.0));
    s.acc_y        = 0.1f * static_cast<float>(std::cos(t * 2.0));
    s.acc_z        = -9.81f;
    s.gyro_x       = 0.0f;
    s.gyro_y       = 0.0f;
    s.gyro_z       = 0.01f * static_cast<float>(std::sin(t * 0.5));
    return s;
}
