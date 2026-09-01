import { Search01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useEffect, useRef, useState } from "react";

import { Field } from "@/components/ui/field";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";

export const CAMERA_LIST_SEARCH_DEBOUNCE_MS = 300;

interface CameraListSearchProps {
  query: string | undefined;
  onQueryChange: (query: string | undefined) => void;
}

/**
 * 搜索框保留即时输入状态，但只有防抖结束后才更新 URL。
 *
 * 外部前进/后退会改变 `query`。此时先取消旧计时器再同步输入值，避免旧字符在 300ms 后
 * 覆盖 Router 已恢复的状态。
 */
export function CameraListSearch({
  query,
  onQueryChange,
}: CameraListSearchProps) {
  const [inputValue, setInputValue] = useState(query ?? "");
  const [inputQuery, setInputQuery] = useState(query);
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  function cancelPendingNavigation() {
    if (debounceTimer.current !== undefined) {
      clearTimeout(debounceTimer.current);
      debounceTimer.current = undefined;
    }
  }

  if (inputQuery !== query) {
    // React 推荐的“渲染期间调整状态”模式让外部 URL 变化立即反映到输入框，避免 effect 后再闪动旧值。
    setInputQuery(query);
    setInputValue(query ?? "");
  }

  useEffect(() => {
    // query 变化或组件卸载时，cleanup 取消上一轮输入创建的计时器。
    return () => {
      if (debounceTimer.current !== undefined) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = undefined;
      }
    };
  }, [query]);

  function scheduleQueryChange(nextValue: string) {
    setInputValue(nextValue);
    cancelPendingNavigation();

    const normalizedQuery = nextValue.trim() || undefined;
    if (normalizedQuery === query) {
      return;
    }

    debounceTimer.current = setTimeout(() => {
      debounceTimer.current = undefined;
      onQueryChange(normalizedQuery);
    }, CAMERA_LIST_SEARCH_DEBOUNCE_MS);
  }

  return (
    <Field className="min-w-0 flex-1">
      <InputGroup>
        <InputGroupInput
          id="camera-list-search"
          type="search"
          aria-label="搜索摄像头"
          value={inputValue}
          maxLength={100}
          autoComplete="off"
          placeholder="按名称或 IPv4 搜索"
          onChange={(event) => scheduleQueryChange(event.currentTarget.value)}
        />
        {/* 搜索图标只提示输入用途，搜索框已有可访问名称，因此不重复朗读图标。 */}
        <InputGroupAddon aria-hidden="true">
          <HugeiconsIcon icon={Search01Icon} strokeWidth={2} />
        </InputGroupAddon>
      </InputGroup>
    </Field>
  );
}
