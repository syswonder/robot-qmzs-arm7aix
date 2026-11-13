# config/handeye/ —— 手眼标定产物（本目录不入库）

`qmzs_grasp` 通过清单里的两个路径读取标定：

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `calibration.json` | 桌面单应矩阵（去畸变像素 → base_link XY，米）+ 相机内参 + 有效区域 | `pixel_to_pose` / `pick` 把图像坐标换成基座坐标 |
| `grasp_orientation.json` | 目标法兰 Z（米）+ 四元数 xyzw（base_link） | 固定抓取高度与姿态；缺省时用清单里的 `default_z_m` / `default_quaternion_xyzw` |
| `image_to_robot_xy.npy` | `calibration.json` 里单应矩阵的备份 | 由标定工具导出，可留作对照 |

## 怎么生成

1. 用 handeye-calibration 对这台机器做相机内参与桌面标定；
2. 相机分辨率必须是 **640×480@15 MJPG**（与 `robonix_manifest.yaml` 里的 `orbbec_camera` 配置一致），
   否则像素坐标与单应矩阵对不上；
3. 导出上述文件，拷入本目录（保持文件名不变，或在清单里改 `calibration_path` / `orientation_path`）；
4. 技能按文件 mtime 自动重载，重标定后不需要改代码。

## 为什么不入库

标定结果与现场安装几何强相关，换机器/挪相机就失效；发布出去会误导读者的抓取参数。
`.gitignore` 已忽略本目录下的 `*.json`、`*.npy`、`*.yaml`，`git status` 里保持干净即正确。

未标定时：`detect_object`、`snapshot`、`calibration_status` 可用；`pixel_to_pose`、`pick` 会明确报错。
