import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { Button } from "@/components/ui/button";

test("renders and handles a click", async () => {
  const user = userEvent.setup();
  const handleClick = vi.fn();

  render(<Button onClick={handleClick}>开始分析</Button>);

  const button = screen.getByRole("button", { name: "开始分析" });
  expect(button).toBeEnabled();

  await user.click(button);

  expect(handleClick).toHaveBeenCalledOnce();
});
