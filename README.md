# 无畏契约死亡自动摸鱼

Windows 桌面工具：确认自己在《VALORANT》国际服对局中死亡后，切换到 Microsoft Edge 的Threads页面；下一回合购买阶段开始时，暂停视频并切回游戏。再次死亡时会尝试续播上次的视频。

程序通过屏幕画面判断死亡状态，读取本机 `ShooterGame.log` 判断回合阶段。不读取游戏内存，不向游戏进程注入代码。

## 下载与启动

1. 从 [Releases](https://github.com/MuffinHeadOo/valorant-death-switcher/releases/latest) 选择下载：
   - **单文件版** `ValorantDeathSwitcher-v0.1.0-standalone.exe`：直接运行，首次启动会先解压依赖，可能较慢。
   - **文件夹版** `ValorantDeathSwitcher-v0.1.0-win-x64.zip`：解压后运行 `ValorantDeathSwitcher/ValorantDeathSwitcher.exe`。不要只取出其中的 EXE；它需要旁边的 `_internal` 文件夹。
2. 需要 Windows x64 和 Microsoft Edge。启动所选版本。
3. 检查“Threads 网址”和“日志路径”。日志路径留空时，程序自动寻找国际服 `ShooterGame.log`；找不到时可点击“选择文件”。
4. 勾选“自动切屏”，点击“开始运行”。停止时点击“停止运行”。未勾选“自动切屏”时只记录识别事件，适合先检查当前游戏设置下的识别效果。

首次使用 Edge 专用窗口可能需要登录Threads。程序运行时请勿同时打开多个实例。

## 工作方式与适用范围

| 场景 | 行为 |
| --- | --- |
| 标准回合战斗阶段，游戏在前台，画面连续确认本人死亡 | 打开或切到同一个 Edge 窗口，并尝试播放视频 |
| 下一回合购买阶段开始 | 暂停视频，尝试切回游戏 |
| 黑屏、画面捕获失败、计分板遮挡或死亡证据不足 | 不触发死亡切屏，界面显示当前状态 |
| 死斗、乱斗、训练场或无法确认回合模式 | 不执行自动切屏 |

目前使用已验证的国际服标准回合日志识别爆破和极速模式的购买阶段。程序会自动寻找游戏窗口和画面区域，但不同分辨率、独占全屏、无边框全屏、窗口化以及游戏更新后的实际效果仍会受显卡驱动和 HUD 布局影响。Windows 可能拒绝后台程序切回游戏；这时界面会记录故障。

## 常见问题

**死亡后没有切到浏览器**

- 确认已勾选“自动切屏”，界面显示标准回合、战斗阶段，并且游戏在前台。
- 查看“捕获”“识别”“判断原因”和事件记录。无法捕获有效画面时程序不会猜测死亡。
- 第一次打开 Edge 可能比之后慢；购买阶段启动程序有助于预热浏览器。

**购买阶段没有切回游戏**

- 查看事件记录是否出现“购买阶段开始”。如果没有，检查日志路径和当前游戏模式。
- 若事件记录显示 Windows 拒绝切回游戏，可手动切回。程序不会向游戏注入或模拟游戏操作。

**Threads页面或视频没有恢复**

- Edge 使用独立的资料目录，首次需要重新登录。关闭专用窗口后，下一次死亡会尝试重新打开。
- 网页播放器可能在切换内容或重新加载后更换视频元素；此时自动续播不能保证成功。

**程序启动失败**

- 保持发布包目录完整，检查 `%LOCALAPPDATA%\ValorantDeathSwitcher\crash.log`。
- 可通过 [问题反馈模板](https://github.com/MuffinHeadOo/valorant-death-switcher/issues/new/choose) 报告版本、Windows 版本、游戏模式、分辨率、显示模式，以及界面状态和相关错误。提交日志前请自行检查并删去不想公开的路径或账号信息。

## 本地数据与隐私

- 配置：`%LOCALAPPDATA%\ValorantDeathSwitcher\settings.json`
- 事件记录：同目录 `events.log`
- 启动异常：同目录 `crash.log`
- Edge 专用资料：同目录 `edge-profile/`

程序默认不保存整屏截图，也不上传识别画面、游戏日志或设置。网页内容由 Edge 直接访问你填写的网址。上述本地数据不会包含在源码仓库或发布包中。

## 从源码运行与构建

需要 Windows、Python 3.12 x64 和 Microsoft Edge。在项目目录执行：

```powershell
py -3.12 -m venv .venv-official
& .\.venv-official\Scripts\python.exe -m pip install -e . pytest PyInstaller
& .\run.ps1
```

运行测试和打包：

```powershell
& .\.venv-official\Scripts\python.exe -m pytest -q
& .\build.ps1
& .\build-onefile.ps1
```

文件夹版输出位于 `dist/ValorantDeathSwitcher/`，单文件版输出位于 `dist-onefile/`。其中 `local-data/` 为本机测试样本与开发环境，不进入 Git 仓库或发布包；缺少本机原始截图时，对应回放测试会跳过。发布时可将两个版本都放入 GitHub Release。

本项目为非官方工具，与 Riot Games、Threads及 Microsoft 无关联。

本仓库当前未添加开源许可证；如需复用或再发布源码，请先联系仓库所有者。

联系邮箱：[1608175635@qq.com](mailto:1608175635@qq.com)。
