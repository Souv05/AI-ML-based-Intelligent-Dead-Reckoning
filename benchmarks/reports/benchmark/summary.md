# GNSS-blackout drift benchmark

trips scored: 50   (skipped 22)

ISRO target: final horizontal drift <= 10% of outage distance.

| scenario   | speed_source   | heading_source   |   n |   pass_rate |   drift_pct_median |   drift_pct_p90 |   final_drift_m_median |   final_drift_m_p90 |
|:-----------|:---------------|:-----------------|----:|------------:|-------------------:|----------------:|-----------------------:|--------------------:|
| every_2min | truth          | truth            | 482 |       0.998 |               0.26 |            1.02 |                   1.8  |                9.56 |
| every_2min | obd            | veh_yawrate      | 482 |       0.573 |               7.8  |           53.6  |                  61.66 |              434.37 |
| every_2min | truth          | veh_yawrate      | 482 |       0.573 |               7.76 |           53.58 |                  61.36 |              434.2  |
| every_2min | wheel_speed    | veh_yawrate      | 482 |       0.571 |               7.76 |           53.59 |                  60.97 |              434.4  |
| every_2min | hold           | truth            | 482 |       0.353 |              15.82 |           61.32 |                 124.17 |              391.81 |
| every_2min | obd            | gps_hold         | 482 |       0.237 |              28.37 |          109.61 |                 224.81 |              629.02 |
| every_2min | hold           | imu_aligned      | 482 |       0.102 |              46.57 |          135.14 |                 350.77 |              735.66 |
| every_2min | imu_integrate  | imu_aligned      | 482 |       0.037 |              64.7  |          195.09 |                 490.66 |             1157.45 |
| isro_1km   | truth          | truth            |  47 |       1     |               0.17 |            0.45 |                   1.69 |                4.36 |
| isro_1km   | hold           | truth            |  47 |       0.319 |              16.06 |           70.54 |                 159.45 |              705.91 |
| isro_1km   | obd            | veh_yawrate      |  47 |       0.277 |              21.74 |           99.74 |                 217.51 |              944.49 |
| isro_1km   | truth          | veh_yawrate      |  47 |       0.277 |              22.09 |           99.5  |                 221.04 |              944.04 |
| isro_1km   | wheel_speed    | veh_yawrate      |  47 |       0.277 |              21.7  |           98.95 |                 217.16 |              942.27 |
| isro_1km   | obd            | gps_hold         |  47 |       0.128 |              37.01 |          122.75 |                 370.3  |             1227.6  |
| isro_1km   | hold           | imu_aligned      |  47 |       0.064 |              56.32 |          120.54 |                 563.14 |             1151.02 |
| isro_1km   | imu_integrate  | imu_aligned      |  47 |       0.021 |              68.74 |          279.16 |                 687.56 |             2638.84 |
| isro_60s   | truth          | truth            |  50 |       1     |               0.22 |            0.47 |                   1.57 |                3.27 |
| isro_60s   | obd            | veh_yawrate      |  50 |       0.42  |              23.47 |           89.48 |                 157.64 |              701.09 |
| isro_60s   | truth          | veh_yawrate      |  50 |       0.42  |              23.79 |           89.13 |                 157.89 |              701.65 |
| isro_60s   | wheel_speed    | veh_yawrate      |  50 |       0.42  |              23.81 |           88.52 |                 156.65 |              700.58 |
| isro_60s   | hold           | truth            |  50 |       0.38  |              14.62 |           53.27 |                 105.8  |              389.25 |
| isro_60s   | obd            | gps_hold         |  50 |       0.16  |              36.7  |          114.76 |                 239.01 |              704.75 |
| isro_60s   | hold           | imu_aligned      |  50 |       0.1   |              45.92 |          100.51 |                 394.29 |              729.91 |
| isro_60s   | imu_integrate  | imu_aligned      |  50 |       0.06  |              62.26 |          220.44 |                 540.65 |             1648.68 |
| tunnels    | truth          | truth            | 210 |       0.986 |               0.27 |            0.83 |                   1.04 |                2.3  |
| tunnels    | obd            | veh_yawrate      | 210 |       0.624 |               5.82 |           52.65 |                  21.56 |              156.05 |
| tunnels    | wheel_speed    | veh_yawrate      | 210 |       0.624 |               6.21 |           52.84 |                  22.11 |              155.18 |
| tunnels    | truth          | veh_yawrate      | 210 |       0.619 |               6.12 |           53.86 |                  21.94 |              154.85 |
| tunnels    | hold           | truth            | 210 |       0.39  |              15.29 |           66.42 |                  51.42 |              174.75 |
| tunnels    | obd            | gps_hold         | 210 |       0.271 |              22.61 |          100.62 |                  80.58 |              255.08 |
| tunnels    | hold           | imu_aligned      | 210 |       0.1   |              36.03 |          113.4  |                 135.02 |              309.44 |
| tunnels    | imu_integrate  | imu_aligned      | 210 |       0.067 |              43.17 |          152.51 |                 160.88 |              436.99 |

## skipped trips

- Vta/Vta03: not benchmark-usable
- Vta/Vta05: not benchmark-usable
- Vta/Vta09: not benchmark-usable
- Vta/Vta11: not benchmark-usable
- Vta/Vta13: not benchmark-usable
- Vta/Vta19: not benchmark-usable
- Vta/Vta20: not benchmark-usable
- Vta/Vta25: not benchmark-usable
- Vtb/Vtb03: not benchmark-usable
- Vtb/Vtb04: not benchmark-usable
- Vtb/Vtb06: not benchmark-usable
- Vtb/Vtb07: not benchmark-usable
- Vtb/Vtb09: not benchmark-usable
- Vtb/Vtb10: not benchmark-usable
- Vtb/Vtb11: not benchmark-usable
- Vtb/Vtb12: not benchmark-usable
- Vw/Vw01: not benchmark-usable
- Vw/Vw09: not benchmark-usable
- Vw/Vw13: not benchmark-usable
- Vw/Vw15: not benchmark-usable
- Vw/Vw17: not benchmark-usable
- Y/Y1: not benchmark-usable
