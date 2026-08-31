import { isCommonAssetRequest } from "msw";
import { setupWorker } from "msw/browser";

import {
  createCamerasMswScenario,
  isCamerasMswScenarioName,
  WHEP_TEST_WHEP_URLS,
} from "@/mocks/cameras/scenarios";

const worker = setupWorker();

function isWhepPlayerRequest(scenarioName: string, request: Request) {
  if (scenarioName !== "whep-player") {
    return false;
  }

  const requestUrl = new URL(request.url);
  const pathAllowed = WHEP_TEST_WHEP_URLS.some((value) => {
    const whepUrl = new URL(value);
    return (
      requestUrl.origin === whepUrl.origin &&
      (requestUrl.pathname === whepUrl.pathname ||
        requestUrl.pathname.startsWith(`${whepUrl.pathname}/`))
    );
  });
  const methodAllowed = ["OPTIONS", "POST", "PATCH", "DELETE"].includes(
    request.method,
  );

  return pathAllowed && methodAllowed;
}

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

      // 只有标准播放器场景的两个固定 WHEP endpoint 和各自返回的 Session 子路径可以访问真实 MediaMTX。
      // 不能按 8889 端口整体放行，否则漏写的媒体请求会绕过 MSW 的开发期保护。
      if (isWhepPlayerRequest(scenarioName, request)) {
        return;
      }

      // Codex/Playwright 日志端点和项目 favicon 都不是业务 API。日志请求如果继续交给 MSW 的
      // error 策略，MSW 打印的错误还会再次触发同一请求；favicon 则由 Vite 直接提供。
      if (pathname === "/__tsd/console-pipe" || pathname === "/favicon.ico") {
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
