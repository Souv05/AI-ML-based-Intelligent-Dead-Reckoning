# STEP 15C - Process Model Audit

## OLD (Step 14) - velocity hard-assignment
```python
    def predict(self, dt, v_fwd):
        E, N, vE, vN, psi = self.x
        s, c = math.sin(psi), math.cos(psi)
        vE_n, vN_n = v_fwd * s, v_fwd * c
        E_n = E + 0.5 * (vE + vE_n) * dt
        N_n = N + 0.5 * (vN + vN_n) * dt
        F = np.eye(5)
        F[0, 2] = 0.5 * dt;  F[0, 4] = 0.5 * dt * v_fwd * c
        F[1, 3] = 0.5 * dt;  F[1, 4] = -0.5 * dt * v_fwd * s
        F[2, 2] = 0.0;       F[2, 4] = v_fwd * c
        F[3, 3] = 0.0;       F[3, 4] = -v_fwd * s
        self.x = np.array([E_n, N_n, vE_n, vN_n, psi])
        self.P = F @ self.P @ F.T + np.diag(self.Q_psd) * dt
        self._clamp_P()
```
`vE_n, vN_n = v_fwd * s, v_fwd * c` overwrites velocity from (v_fwd, psi) on every call, so `v_lateral(x) = vE*cos(psi) - vN*sin(psi) = v_fwd*sin(psi)*cos(psi) - v_fwd*cos(psi)*sin(psi) = 0` **exactly**, for any v_fwd/psi - confirmed in 15B across all NHC candidates.

## 10-item audit
```json
{
  "1. state definition": "x = [E, N, vE, vN, psi]  (5-state, unchanged in 15C)",
  "2. predict() function": "trapezoidal integration; velocity HARD-ASSIGNED from (v_fwd, psi) every call",
  "3. velocity propagation": "vE_n=v_fwd*sin(psi), vN_n=v_fwd*cos(psi) - NOT integrated independently -> ROOT CAUSE",
  "4. heading propagation": "psi unchanged in predict (constant heading + Q_psi process noise); gyro verified unusable (corr~0)",
  "5. position propagation": "trapezoidal: E += 0.5*(vE+vE_n)*dt, N += 0.5*(vN+vN_n)*dt",
  "6. process covariance Q": "[8.0, 8.0, 1.0, 1.0, 0.004873878716587337] ['m^2/s', 'm^2/s', '(m/s)^2/s', '(m/s)^2/s', 'rad^2/s']",
  "7. GNSS update": "z=[ref_x,ref_y], H=[[1,0,0,0,0],[0,1,0,0,0]], R=diag(25,25), Joseph form, gain-ramped at reacquisition",
  "8. GRU velocity usage": "v_fwd argument to predict() - HARD-ASSIGNED into vE,vN, never a measurement -> SECOND ROOT CAUSE",
  "9. GNSS outage handling": "predict-only inside outage window; GNSS update masked by (not in_outage) and gnss_available==1",
  "10. covariance update": "Joseph form + diagonal-clamp covariance ceiling (_clamp_P), correlation-preserving"
}
```

## NEW (Step 15C) - independent velocity states
Constant-velocity-between-updates prediction (section 6 of the notebook): vE, vN, psi pass through predict() unchanged (only position advances kinematically, E+=vE*dt, N+=vN*dt); process noise Q (reused unchanged from Step 14) represents real unmodelled acceleration. Accelerometer-driven propagation was considered and rejected - documented, not silently assumed: the project EDA found phone longitudinal-accel coupling to true vehicle dynamics weak on all trips (best ~0.4), and Step 13C's gravity-removed accelerometer double-integration produced order-of-magnitude worse drift than a plain velocity/heading model - so this is the smallest defensible choice, not an accelerometer integration.

## GRU velocity: hard assignment -> measurement
OLD: `predict(dt, v_fwd)` used v_fwd to directly overwrite vE,vN. NEW: `update_ai_velocity(v_gru, sig_ai)` treats v_gru as a measurement of h_ai(x)=v_forward(x) with R_AI=sig_ai^2, sig_ai=5.070742 m/s (reused = frozen 12D GRU test RMSE, not tuned here). The EKF may now disagree with the GRU (bounded by the Kalman gain), rather than being forced to equal it.

## NHC: redundant zero-innovation update -> real constraint
Section 9 (sanity Test A) confirms NHC innovation is now nonzero for a state with lateral velocity error, and the update measurably reduces |v_lateral| - the precondition that was absent in Step 14/15A/15B integration is now met.
