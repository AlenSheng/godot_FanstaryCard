# Google Play Android 构建门禁

本项目的 Android 正式发布预设是 `client/export_presets.cfg` 中的 `Android Production`。它固定使用：

- AAB 输出：`builds/android/Relicbound.aab`
- 包名：`com.relicbound.game`
- target SDK：36
- min SDK：26
- 仅 arm64-v8a
- 正式构建关闭本地数据备份
- 正式预设要求签名，且带有 `google_play`、`production` 构建特性

签名私钥、别名和密码不得提交到 Git。导出前必须在本机或 CI 的安全凭据中设置：

```text
GODOT_ANDROID_KEYSTORE_RELEASE_PATH
GODOT_ANDROID_KEYSTORE_USER
GODOT_ANDROID_KEYSTORE_PASSWORD
```

执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\export_android_release.ps1
```

导出成功只代表仓库侧生成了结构正确的 AAB；仍需在 Play Console 完成 Play App Signing、内部测试上传、签名校验、设备矩阵和审核材料。真实上传密钥不存放在本仓库。
