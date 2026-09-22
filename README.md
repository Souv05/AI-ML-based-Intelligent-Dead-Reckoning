# 🛰️ SIH 2026 — AI-ML Based Intelligent Dead Reckoning

### ISRO Problem Statement — PS 26168

<p align="center">

**AI-Assisted • GNSS-Resilient • Real-Time Navigation**

</p>

> **Continuous navigation when GNSS becomes unavailable or unreliable.**

---

## 🎯 Problem

GNSS can fail in tunnels, urban canyons, dense infrastructure and GNSS-denied environments.

Pure inertial Dead Reckoning continues without GNSS, but **sensor errors accumulate and cause position drift**.

### Objective

**Maintain continuous positioning during GNSS outages while controlling drift and seamlessly recovering when GNSS returns.**

---

# 💡 Solution

Our system combines **IMU + AI velocity estimation + EKF + Non-Holonomic Constraints + ZUPT + GNSS + map/road information**.

```text
                 IMU + GNSS
                     │
                     ▼
             Filtering / Calibration
                     │
                     ▼
                  GRU-v2
             AI Speed Estimation
                     │
                     ▼
                EKF + NHC
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
        GNSS        ZUPT      Map/Road
          │          │          │
          └──────────┼──────────┘
                     ▼
          Intelligent Navigation
```

### Core principle

> **AI estimates motion. Physics constrains motion. Sensor fusion produces the navigation solution.**

---

# ✅ Current Implementation

| Module                               |     Status     |
| ------------------------------------ | :------------: |
| IO-VNBD data pipeline                |        ✅       |
| ENU reference generation             |        ✅       |
| GNSS blackout generation             |        ✅       |
| Sequence-wise split & leakage checks |        ✅       |
| Classical NHC Dead Reckoning         |        ✅       |
| Drift benchmark                      |        ✅       |
| GRU-v2 speed estimation              |        ✅       |
| IMU filtering & calibration          |        ✅       |
| EKF sensor fusion                    |        ✅       |
| NHC                                  |        ✅       |
| ZUPT                                 |        ✅       |
| GNSS outage detection                |        ✅       |
| GNSS re-acquisition                  |        ✅       |
| Map / road-bearing assistance        |        ✅       |
| Real-time navigation engine          |        ✅       |
| WebSocket navigation output          |        ✅       |
| Flutter / ONNX                       |        ✅       |
| Vehicle hardware                     |        ✅        |

---

# 🧠 AI + Sensor Fusion

### GRU-v2

The current model estimates **forward speed from sequential IMU features**.

```text
IMU Sequence
     ↓
   GRU-v2
     ↓
Forward Speed
     ↓
    EKF
```

### EKF State

```text
X = [East, North, vEast, vNorth, Heading]
```

The filter combines:

**IMU + GRU speed + GNSS + NHC + ZUPT + road bearing**

to estimate the navigation state.

---

# 📡 GNSS → DR → GNSS

The system supports controlled navigation-mode transitions:

```text
             GNSS HEALTH
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
     HEALTHY             INVALID
        │                   │
        ▼                   ▼
   GNSS-AIDED           DR-ACTIVE
                            │
                      IMU + AI + EKF
                            │
                       GNSS RETURNS
                            ▼
                    GNSS-REACQUIRE
                            │
                            ▼
                       GNSS-AIDED
```

### Navigation modes

`GNSS_AIDED` · `DR_ACTIVE` · `GNSS_REACQUIRE`

---

# 📊 IO-VNBD Data Foundation

The original data pipeline prepares synchronized phone and vehicle data for modelling and evaluation.

```text
Inventory
   ↓
Synchronization
   ↓
Canonical Schema
   ↓
ENU Coordinates
   ↓
GNSS Blackout Mask
   ↓
Temporal Windows
   ↓
Sequence Split
   ↓
Leakage Check
   ↓
Processed Dataset
```

Raw data under `dataset/IO-VNBD/` is never modified.

---

# 🧪 Drift Benchmark

The project includes a synthetic GNSS-blackout benchmark with a baseline **non-holonomic dead-reckoning engine**.

```text
Real Trip
   ↓
GNSS Blackout
   ↓
Dead Reckoning
   ↓
Position Drift
   ↓
Metrics
```

The benchmark evaluates performance against the stated ISRO target:

> **Drift < 10% of distance travelled**

---

# 🚀 SIH Finale Upgrade Roadmap

```text
CURRENT SYSTEM
      │
      ▼
🧠 Self-Aware Sensors
Health • Bias • Adaptive Noise
      │
      ▼
🤖 Next-Gen AI
Velocity • Heading • Uncertainty
      │
      ▼
🔗 Multi-Sensor Fusion
Wheel • CAN • OBD-II • External IMU
      │
      ▼
📡 GNSS Intelligence
Quality • Anomaly • Predictive Outage
      │
      ▼
🗺️ Context-Aware Navigation
Map • Road • Motion Constraints
      │
      ▼
⚡ Edge Autonomy
On-Device • Low Latency • Offline
      │
      ▼
🚗 Vehicle Deployment
Android • ESP32 • CAN • ROS 2
```

---

# 🔮 Planned Features

| Upgrade                              | Goal                         |
| ------------------------------------ | ---------------------------- |
| 🧠 Sensor health & adaptive fusion   | Improve reliability          |
| 🤖 Multi-task AI + uncertainty       | Improve estimation           |
| 🔗 CAN / OBD-II / wheel-speed fusion | Vehicle-grade sensing        |
| 📡 GNSS anomaly detection            | Better GNSS trust management |
| 🗺️ Advanced map/context constraints | Reduce drift                 |
| ⚡ On-device optimization             | Offline real-time operation  |
| 🚗 Physical vehicle validation       | Real-world deployment        |

---

# 🏆 Why This Approach

### **AI-Assisted**

Learns motion information from sequential IMU data.

### **Physics-Constrained**

Uses EKF, NHC and ZUPT rather than relying solely on AI.

### **GNSS-Resilient**

Continues navigation during GNSS outages.

### **Real-Time**

Designed around continuous navigation output.

### **Scalable**

Sensor adapters allow future vehicle sensors without redesigning the navigation core.

---

# 📈 Validation

| Scenario            | Measure                  |
| ------------------- | ------------------------ |
| 🟢 GNSS Available   | Baseline navigation      |
| 🔴 GNSS Blackout    | Position drift           |
| 🟡 GNSS Degradation | Mode switching           |
| 🔄 GNSS Recovery    | Re-acquisition           |
| ⚡ Real-Time         | Latency / resource usage |

### Key metrics

**Position Error · Drift Rate · Velocity Error · Heading Error · Re-acquisition Error · Inference Latency**

---

# 🛠️ Technology Stack

```text
AI/ML        → Python • PyTorch • GRU • ONNX • NumPy
Navigation   → EKF • Dead Reckoning • NHC • ZUPT
Sensors      → IMU • GNSS
Real-Time    → Python • WebSocket
Edge         → Flutter • ONNX Runtime
Future       → CAN • OBD-II • ESP32 • Camera/VIO • ROS 2
```

---

# 📂 Repository

```text
AI-ML-based-Intelligent-Dead-Reckoning/
│
├── dataset/
├── src/
│   ├── data/
│   └── iovnbd/
├── scripts/
├── tests/
├── artifacts/
├── outputs/
├── data/
├── DATA_PREP_REPORT.md
├── requirements.txt
└── README.md
```

---

# ⚡ Quick Start

```bash
git clone https://github.com/Devnil434/AI-ML-based-Intelligent-Dead-Reckoning.git
cd AI-ML-based-Intelligent-Dead-Reckoning
python -m pip install -r requirements.txt
```

### Data preparation

```bash
python -m pytest -q tests/test_data_pipeline.py
python scripts/prepare_dataset.py
```

### Drift benchmark

```bash
python scripts/01_build_catalog.py
python scripts/02_eda_report.py
python scripts/03_run_drift_benchmark.py
```

---

# 🏁 Final Vision

```text
             TODAY
               │
      IMU + GRU + EKF + NHC
               │
               ▼
       GNSS-RESILIENT DR
               │
               ▼
            FUTURE
               │
       Multi-Sensor + AI
               │
               ▼
       GNSS-Resilient
               │
               ▼
        Edge Autonomy
               │
               ▼
       Vehicle Deployment
```

> ## 🚀 From AI-assisted Dead Reckoning to a resilient, multi-sensor intelligent navigation platform.

### 🇮🇳 Smart India Hackathon 2026

**ISRO PS 26168**
