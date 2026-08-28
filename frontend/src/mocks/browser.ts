import { isCommonAssetRequest } from "msw";
import { setupWorker } from "msw/browser";

import {
  createCamerasMswScenario,
  isCamerasMswScenarioName,
} from "@/mocks/cameras/scenarios";

const worker = setupWorker();

/** 开发环境只接受显式场景名；拼写错误直接失败，避免无声访问真实服务。 */
export async function startBrowserMocking(scenarioName: string) {
  if (!isCamerasMswScenarioName(scenarioName)) {
    throw new Error(`未知的 Cameras MSW 场景：${scenarioName}`);
  }

  worker.use(...createCamerasMswScenario(scenarioName));
  await worker.start({
    // CameraDetail 含密码和完整 RTSP URL，禁止 MSW 把已处理请求的响应体打印到开发终端。
    // 未处理请求仍由下方回调报错，因此静默正常请求不会掩盖缺失的业务 handler。
    quiet: true,
    onUnhandledRequest(request, print) {
      const { pathname } = new URL(request.url);

      // Codex/Playwright 会把浏览器日志发回这个仅供开发工具使用的端点。它不是业务 API，
      // 如果继续交给 MSW 的 error 策略，MSW 自己打印的错误又会触发同一请求并形成递归日志。
      if (pathname === "/__tsd/console-pipe") {
        return;
      }

      // 自定义回调会关闭 MSW 默认的静态资源忽略规则，需显式恢复，否则 Vite 模块和字体
      // 会被当成漏写的 API mock。该判断只放行 MSW 识别出的常见静态资源。
      if (isCommonAssetRequest(request)) {
        return;
      }

      // 其余未声明请求仍然报错，保证开发场景不会无声访问真实 Cameras API。
      print.error();
    },
  });
}
