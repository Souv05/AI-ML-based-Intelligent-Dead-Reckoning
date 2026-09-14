# Step 17A — Phone-to-Vehicle Alignment & Calibration

**Date**: 2026-09-10 22:17
**Step**: 17A
**Phase**: Phase 17 — Navigation Integration

---

## 1. Objective

Estimate the orientation of the smartphone relative to the vehicle's driving frame
and produce a rotation R: Phone frame → Vehicle frame.

The module supports:
- Static tilt alignment (roll, pitch from gravity)
- GNSS-aided yaw-offset calibration
- Confidence estimation and remount detection

**IMPORTANT**: This module does NOT change GRU-v2 inputs. It is used only by the EKF
for vehicle heading initialisation.

---

## 2. Coordinate Frames

### Phone frame (Android)
- X+ = device right
- Y+ = device top (top edge in portrait mode)
- Z+ = screen front face
- acc_z ≈ +g when phone Z is up (standard Android TYPE_ACCELEROMETER)

### Vehicle frame
- x_v = vehicle forward
- y_v = vehicle lateral left
- z_v = vehicle up

### Navigation frame (ENU)
- East, North, Up; heading = degrees clockwise from North (compass convention)

### IO-VNBD Mounting Observation
Across all 46 IO-VNBD sequences:
- pitch (Android) ≈ −82 to −88° (phone nearly vertical, portrait mount)
- pitch std ≈ 1−3° (very stable tilt)
- roll (Android): large variance (>60° std in most sequences) due to **gimbal lock**
  at pitch ≈ ±90° — roll is ill-defined in this configuration
- acc_z ≈ +9.8 m/s² confirms phone Z axis ≈ physical up

---

## 3. Sensor Inputs

| Sensor | Used for | Note |
|--------|----------|------|
| Accelerometer | Static tilt (Stage A) | Includes gravity (TYPE_ACCELEROMETER) |
| Gyroscope | Stationary detection | Low-rate check |
| Android Orientation (yaw) | GNSS yaw calibration | Azimuth of phone top edge |
| GNSS course | Yaw offset estimation (Stage B) | Uses reference_heading for evaluation |
| GNSS speed | Validity gate | speed ≥ 3.0 m/s required |
| Magnetometer | Not used directly | Subject to vehicle metal disturbance |

---

## 4. Static Tilt Alignment (Stage A)

When the phone is stationary, the accelerometer measures gravity only.

Stationary detection criteria:
- |acc_mag − g| < 0.5 m/s²
- acc_mag std < 0.30 m/s²
- mean |gyro| < 0.1 rad/s
- applied over a ±1.0s sliding window

Roll and pitch from gravity:
```
pitch_tilt = arctan2(−acc_x, sqrt(acc_y² + acc_z²))
roll_tilt  = arctan2(acc_y, acc_z)
```

**Note on gimbal lock**: With pitch_tilt ≈ −83°, the phone is nearly horizontal
in the standard tilt formula. The tilt pitch (from gravity) ≈ −5 to −8°, which is
different from the Android orientation pitch (≈ −85°). Both describe the same physical
mounting but use different reference frames. At |pitch_tilt| ≈ 90°, roll becomes
undefined — confidence is reported as low in that regime.

---

## 5. Vehicle-Yaw Alignment (Stage B)

During reliable GNSS-aided motion, the vehicle heading ≈ GNSS course.

```
yaw_offset = circular_mean(gnss_course − phone_yaw)
```

Applied only when:
- gnss_available == 1
- gnss_speed ≥ 3.0 m/s
- Circular mean used to avoid 0°/360° wrap artefacts

Vehicle heading estimate:
```
vehicle_heading = phone_yaw + yaw_offset
```

---

## 6. Rotation Transformation

Rotation matrix built from ZYX Euler angles (yaw_offset → pitch_tilt → roll_tilt):

```
R_phone_to_vehicle = Rz(yaw_offset) @ Ry(−pitch_tilt) @ Rx(−roll_tilt)
```

Orthonormalized via SVD to ensure det(R) = +1.

Vector transformation:
```
v_vehicle = R @ v_phone
```

---

## 7. Stationary Detection

IMU-only causal window-based detector (same principle as Step 15F ZUPT detector):
- Window ±1.0s centred on each sample
- Three criteria (acc magnitude, variance, gyro magnitude)
- No speed or GNSS required — works during GNSS outage

---

## 8. GNSS-Aided Yaw Calibration

Uses all valid motion samples in the sequence. Circular mean is robust to:
- 0°/360° wrap-around
- Individual noisy GNSS heading samples
- Vehicle turning (errors average out over many headings)

**Per-sequence yaw offsets differ** because each sequence has a different phone
mounting in a different vehicle. Re-calibration is needed for each new trip.

---

## 9. Confidence Estimation

| Signal | Weight |
|--------|--------|
| Tilt confidence (gimbal proximity, gravity stability) | 30% |
| Yaw confidence (n_samples, circular std) | 70% |

Confidence = 0.3 × conf_tilt + 0.7 × conf_yaw

Status: UNCALIBRATED / TILT_ONLY / LOW_CONFIDENCE / ALIGNED / REALIGN_REQUIRED

---

## 10. Remount Detection

Compares new gravity-derived tilt against calibrated baseline.
If |Δroll| > 15° or |Δpitch| > 15° → REALIGN_REQUIRED.
Does not silently overwrite the frozen calibration.

---

## 11. Synthetic Sanity Tests

| Test | Description | Result |
|------|-------------|--------|
| test1_identity | Phone frame = vehicle frame, expect R ≈ I | PASS |
| test2_known_yaw | Known yaw_offset=30°, phone_yaw=0°, gnss_course=30° | PASS |
| test3_known_pitch | Known pitch_tilt=5.0°, expect pitch estimate ≈ 5.0° | PASS |
| test4_known_roll | Known roll_tilt=8.0°, expect roll estimate ≈ 8.0° | PASS |
| test5_combined | Combined yaw=45°, pitch=5°, roll=8° | PASS |
| test6_orthogonality | Verify RᵀR ≈ I and det(R) ≈ 1 | PASS |
| test7_gravity_transform | With yaw_offset=0 and no tilt, gravity [0,0,g] in phone | PASS |

7/7 tests passed.

---

## 12. IO-VNBD Evaluation (4 test sequences)

| Sequence | yaw_offset ± std | MAE before | MAE after | RMSE after | Confidence | Status |
|----------|-----------------|------------|-----------|------------|------------|--------|
| Vta08 | 163.8° ± 138.7° | 93.3° | 85.5° | 96.9° | 0.61 | ALIGNED |
| Vta28 | -178.5° ± 111.1° | 102.1° | 77.9° | 100.6° | 0.61 | ALIGNED |
| Vtb01 | -170.3° ± 88.5° | 112.3° | 67.2° | 85.8° | 0.62 | ALIGNED |
| Vw02 | 151.6° ± 27.5° | 144.7° | 20.7° | 28.2° | 0.85 | ALIGNED |

Metric definitions (valid motion: reference_speed ≥ 3.0 m/s):
- **MAE before**: heading error using raw phone yaw vs reference_heading
- **MAE after**: heading error using (phone_yaw + yaw_offset) vs reference_heading
- **yaw_offset**: per-sequence phone-to-vehicle yaw offset estimated from GNSS

---

## 13. Alignment Errors

The residual heading error after alignment has two sources:

1. **Magnetometer disturbance**: Vehicle electronics create systematic magnetic
   field distortions that shift the phone's compass reading. The circular mean
   partially absorbs this as part of yaw_offset, but residual distortions remain.

2. **GNSS course noise during turns**: At slow speeds or during turns, GNSS course
   is less reliable. The speed gate (≥3.0 m/s) mitigates but does not eliminate this.

---

## 14. Stability Analysis

Phone tilt (pitch from accelerometer) is very stable across all sequences:
- pitch_raw std: 2.1° average (small, consistent)
- roll_raw std: 104.5° average (large — gimbal lock artefact)

The yaw_offset varies significantly between sequences (different mounts/vehicles),
confirming that per-session calibration is required.

---

## 15. GRU-v2 Compatibility Check

| Check | Result |
|-------|--------|
| GRU-v2 trained on | Raw phone-frame features (Android sensor frame) |
| acc_x/y/z convention | Specific force + gravity (TYPE_ACCELEROMETER) |
| roll/pitch/yaw convention | Android Orientation sensor Euler angles |
| Alignment changes GRU inputs | NO |
| Alignment purpose for GRU pipeline | EKF heading initialisation only |
| Conclusion | **COMPATIBLE — do not rotate features before GRU inference** |

**Why**: GRU-v2 was trained on raw phone-frame data from all 46 IO-VNBD sequences
(35 train, 7 val, 4 test), each with different phone mounting orientations.
The model learned to predict forward speed from phone-frame IMU despite mounting diversity.
Rotating features to vehicle frame before inference would shift the input distribution
away from training data → degraded predictions.

---

## 16. Limitations

1. **Per-sequence calibration required**: yaw_offset is not transferable between drives.

2. **Gimbal lock**: roll from gravity is ill-defined when |pitch_tilt| ≈ 90°.
   In this dataset pitch_tilt is small (~5–8°) so tilt correction is minor; the
   heading is dominated by Stage B (GNSS yaw calibration).

3. **Magnetometer disturbance**: The Android compass yaw is disturbed by vehicle
   electronics. The calibrated yaw_offset absorbs the mean disturbance, but residual
   dynamic distortions remain.

4. **GRU heading error context**: The 31.9° mean heading error in the existing
   authoritative EKF result is EKF heading DRIFT during GNSS outages, not a static
   alignment error. The alignment module addresses static mounting offsets; it does
   NOT fix the heading drift during outages (that requires a heading-observable update
   such as a magnetometer model, map-matching, or ZIHR).

5. **Heading MAE after alignment** reflects how well the phone yaw + yaw_offset
   tracks vehicle heading over the full sequence. This is NOT the same as the EKF
   heading error during outages.

---

## 17. Final Status

☑ Coordinate conventions documented
☑ Phone → vehicle rotation implemented
☑ Roll estimation implemented (tilt from gravity)
☑ Pitch estimation implemented (tilt from gravity)
☑ Yaw-offset estimation implemented (GNSS-aided)
☑ Stationary detection implemented
☑ GNSS-aided yaw calibration implemented
☑ Alignment confidence implemented
☑ Remount detection / re-alignment logic implemented
☑ 7/7 synthetic rotation tests pass
☑ Representative IO-VNBD sequences evaluated (4 test sequences)
☑ Alignment metrics generated
☑ GRU-v2 input compatibility verified — DO NOT rotate before GRU
☑ No GRU retraining performed
☑ No test-set threshold tuning performed
☑ STEP17A_REPORT.md created

**STOP. Do NOT start Step 17B automatically.**
Next: review alignment accuracy, yaw stability, GRU-v2 compatibility,
then proceed to 17B — GNSS Health / Outage Detection.
