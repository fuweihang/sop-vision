# MediaMTX WebRTC reader

`reader.js` 原样取自 MediaMTX `v1.20.1`：

- 来源：<https://raw.githubusercontent.com/bluenviron/mediamtx/v1.20.1/internal/servers/webrtc/reader.js>
- SHA-256：`a802f229b803c33713d4c69c4cc0d480108a5bf384947aeee4aaf04268bf85c1`
- 上游许可证：MIT，见同目录 `LICENSE`

不要直接修改 `reader.js`。升级 MediaMTX 时，必须同时更新来源、SHA-256、类型声明、校验脚本和真实浏览器播放验收。

`load-reader.ts` 是项目维护的动态加载包装器，不属于上游副本。它只负责把非 ES module 的
`reader.js` 放入独立 Vite chunk，不增加或修改 MediaMTX 行为。
