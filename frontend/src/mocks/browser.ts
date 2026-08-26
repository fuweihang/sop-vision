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
  await worker.start({ onUnhandledRequest: "error" });
}
