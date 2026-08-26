/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

import { CAMERA_FIXTURE_SECRET } from "@/mocks/cameras/fixtures";

// jsdom 会把 import.meta.url 表示为浏览器 URL，不能直接交给 node:fs。Vitest 保留的
// import.meta.dirname 是本地测试文件目录，因此从它解析仓库路径不会依赖调用命令的 cwd。
const repositoryRoot = resolve(import.meta.dirname, "../../..");
const openapiSource = readFileSync(
  resolve(repositoryRoot, "contracts/openapi.json"),
  "utf8",
);
const generatedTypeSource = readFileSync(
  resolve(repositoryRoot, "frontend/src/generated/openapi.ts"),
  "utf8",
);

function occurrenceCount(source: string, value: string) {
  return source.split(value).length - 1;
}

describe("Cameras 生成契约敏感数据门禁", () => {
  test("唯一 sentinel 从 OpenAPI 可重复传递到生成类型", () => {
    const openapiOccurrences = occurrenceCount(
      openapiSource,
      CAMERA_FIXTURE_SECRET,
    );
    const generatedOccurrences = occurrenceCount(
      generatedTypeSource,
      CAMERA_FIXTURE_SECRET,
    );

    // sentinel 合法存在于 CameraDetail 与写请求 example；两份生成物计数必须一致，防止生成器
    // 丢失敏感 example 后让安全扫描只验证了一个没有真实 canary 的空路径。
    expect(openapiOccurrences).toBeGreaterThan(0);
    expect(generatedOccurrences).toBe(openapiOccurrences);
  });

  test("生成物不再携带历史上各层分散使用的旧 sentinel", () => {
    const legacySentinels = [
      "foundation-leak-sentinel",
      "domain-leak-sentinel",
      "builder-camera-secret",
      "camera-fixture-leak-sentinel",
      "frontend-camera-password-leak-sentinel",
      "openapi-test-password",
    ];

    for (const legacySentinel of legacySentinels) {
      expect(openapiSource).not.toContain(legacySentinel);
      expect(generatedTypeSource).not.toContain(legacySentinel);
    }
  });
});
