# config/ —— 本体专属配置

这里只放**这台整机**的参数。可复用的驱动/算法改动请提到对应原语或技能仓库。

- `handeye/`：手眼标定产物目录，文件现场生成、**不入库**（`.gitignore` 忽略了 `*.json`、`*.npy`、`*.yaml`）。
  见 [`handeye/README.md`](handeye/README.md)。
- 抓取/放置参数（`arm_provider_id`、`default_z_m`、`approach_height_m` 等）写在 `robonix_manifest.yaml`
  的 `skill[qmzs_grasp].config` 里，不单独建文件。
- 串口/电机参数属于 `arm7aix_controller` 原语的自带配置（`config/arm7aix.yaml`）。**不要**在这里放同名文件：
  原语解析配置时先查包根、再查部署目录，部署侧同名文件会被静默忽略。现场确实要覆盖时，用唯一文件名，例如
  `config/arm7aix.deploy.yaml`，并在清单里写 `sdk_config: config/arm7aix.deploy.yaml`。
