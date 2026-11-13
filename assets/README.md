# assets/ —— 目录页展示资源（可选）

不提供图片也能收录，但**一旦提供就必须完全合规**，否则 `robonix-package-catalog` 的 CI 会失败并点名文件。

- 展示图：`promo/01.jpg`（或 `promo/01.png`），**1600×1000、≤ 2 MB**、JPEG sRGB 三通道 / PNG 8-bit truecolor RGB。
  多语言版本用 `promo/zh/01.*` + `promo/en/01.*`（编号必须一一对应，不能混用两种布局）。
- 图标：`icon.svg` 或 `icon.png`（512×512）。
- 旧写法 `assets/robot.jpg` 已废弃，请用 `promo/01.jpg`。

建议内容：整机照片（含臂、手、相机与基座），加一行型号文字；避免出现他人可识别信息。
