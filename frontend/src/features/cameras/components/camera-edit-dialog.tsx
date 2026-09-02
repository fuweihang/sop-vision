import { zodResolver } from "@hookform/resolvers/zod";
import { Alert02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import type { AxiosInstance } from "axios";
import { useCallback, useEffect, useId, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { cameraQueryKeys } from "@/features/cameras/api/camera-query-keys";
import {
  updateCamera,
  type CameraDetail,
} from "@/features/cameras/api/cameras-api";
import { CameraConnectionFields } from "@/features/cameras/components/camera-connection-fields";
import { CameraEditSourceFields } from "@/features/cameras/components/camera-edit-source-fields";
import {
  mapCameraEditFailure,
  type CameraEditFieldName,
  type CameraEditFormAlert,
} from "@/features/cameras/forms/camera-edit-error-mapping";
import {
  cameraEditFormSchema,
  createEmptyCameraEditSource,
  toCameraEditFormValues,
  toCameraUpdateRequest,
  type CameraEditFormValues,
  type ValidatedCameraEditFormValues,
} from "@/features/cameras/forms/camera-edit-form";
import { fieldErrorMessage } from "@/features/cameras/forms/camera-form-errors";

type ConfirmationKind = "discard-dialog" | "discard-navigation" | "retry";

interface CameraEditDialogProps {
  readonly camera: CameraDetail;
  readonly apiClient: AxiosInstance;
  readonly onClosed: () => void;
}

/**
 * Camera 完整编辑 Dialog。
 *
 * 组件只在用户打开编辑后挂载，因此表单初值来自当时页面正在显示的详情。挂载期间后续轮询只更新
 * `camera` prop 和页面，不会再次调用 `form.reset` 覆盖草稿。
 */
export function CameraEditDialog({
  camera,
  apiClient,
  onClosed,
}: CameraEditDialogProps) {
  const formId = useId();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(true);
  const [confirmation, setConfirmation] = useState<ConfirmationKind>();
  const [formAlert, setFormAlert] = useState<CameraEditFormAlert>();
  const form = useForm<
    CameraEditFormValues,
    unknown,
    ValidatedCameraEditFormValues
  >({
    resolver: zodResolver(cameraEditFormSchema),
    defaultValues: toCameraEditFormValues(camera),
  });
  const { fields, append, remove, move } = useFieldArray({
    control: form.control,
    name: "sources",
  });
  const watchedSources = useWatch({
    control: form.control,
    name: "sources",
  });
  const mutation = useMutation({
    mutationFn: async (request: ReturnType<typeof toCameraUpdateRequest>) => {
      // PUT 响应是敏感 CameraDetail。调用方只消费成功/失败，不把响应留在 Mutation data。
      await updateCamera(camera.camera_id, request, apiClient);
    },
    retry: false,
    gcTime: 0,
  });
  const isSubmitting = form.formState.isSubmitting;
  const isDirty = form.formState.isDirty;
  const shouldProtectLeaving = open && (isDirty || isSubmitting);
  const shouldBlockNavigation = useCallback(
    () => shouldProtectLeaving,
    [shouldProtectLeaving],
  );
  const blocker = useBlocker({
    shouldBlockFn: shouldBlockNavigation,
    enableBeforeUnload: shouldBlockNavigation,
    disabled: !open,
    withResolver: true,
  });
  const defaultSourceFieldId = fields.find(
    (_field, index) => watchedSources[index]?.is_default_preview,
  )?.id;

  useEffect(() => {
    if (blocker.status !== "blocked") {
      return;
    }

    if (isSubmitting) {
      // 提交期间的路由操作直接留在当前页，不能把“是否离开”的决策排队到请求结束之后。
      blocker.reset?.();
      return;
    }

    if (!open || !isDirty) {
      blocker.proceed?.();
    }
  }, [blocker, isDirty, isSubmitting, open]);

  function resetDialogState() {
    form.reset(toCameraEditFormValues(camera));
    form.clearErrors();
    setFormAlert(undefined);
    setConfirmation(undefined);
    mutation.reset();
  }

  function closeDialog() {
    resetDialogState();
    setOpen(false);
    onClosed();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      setOpen(true);
      return;
    }
    if (isSubmitting) {
      return;
    }
    if (isDirty) {
      setConfirmation("discard-dialog");
      return;
    }
    closeDialog();
  }

  function setDefaultSource(fieldId: string) {
    const selectedIndex = fields.findIndex((field) => field.id === fieldId);
    if (selectedIndex < 0) {
      return;
    }

    fields.forEach((_field, index) => {
      form.setValue(
        `sources.${index}.is_default_preview`,
        index === selectedIndex,
        { shouldDirty: true, shouldValidate: true },
      );
    });
  }

  function removeSource(index: number) {
    if (fields.length === 1) {
      return;
    }
    const removedDefault =
      form.getValues(`sources.${index}.is_default_preview`) === true;
    remove(index);
    if (removedDefault) {
      // 删除后数组已经移动；始终把剩余第 0 项设为唯一默认，避免出现暂时无默认源的草稿。
      form.setValue("sources.0.is_default_preview", true, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }

  function focusMappedField(fieldName: CameraEditFieldName) {
    requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(
        `[data-camera-form-field="${fieldName}"], [data-camera-edit-field="${fieldName}"]`,
      );
      target?.focus();
    });
  }

  async function refreshCameraQueries() {
    // 列表查询在详情页通常是 inactive；refetchType=all 才能真正重新读取缓存中的列表分页。
    await Promise.allSettled([
      queryClient.invalidateQueries({
        queryKey: ["cameras"],
        refetchType: "all",
      }),
      queryClient.invalidateQueries({
        queryKey: cameraQueryKeys.camera(camera.camera_id),
        refetchType: "all",
      }),
    ]);
  }

  function applyMutationFailure(error: unknown) {
    const failure = mapCameraEditFailure(error, fields.length);
    if (failure.kind === "alert") {
      setFormAlert(failure.formAlert);
      if (failure.formAlert.kind === "unknown") {
        // 重新读取只更新 Query；当前表单不 reset，也不把 GET 结果与草稿做因果判断。
        void refreshCameraQueries();
      }
      return;
    }

    for (const fieldError of failure.fieldErrors) {
      form.setError(fieldError.fieldName, {
        type: "server",
        message: fieldError.message,
      });
    }
    setFormAlert(failure.formAlert);
    const firstFocusableField = failure.fieldErrors.find(
      (fieldError) => fieldError.focusable,
    )?.fieldName;
    if (firstFocusableField !== undefined) {
      focusMappedField(firstFocusableField);
    }
  }

  async function submitRequest(values: ValidatedCameraEditFormValues) {
    form.clearErrors();
    setFormAlert(undefined);
    try {
      await mutation.mutateAsync(toCameraUpdateRequest(values));
      // 先清除 dirty，避免成功关闭被未保存确认拦截；不使用敏感 PUT 响应写 Query cache。
      form.reset(form.getValues());
      await refreshCameraQueries();
      toast.success("摄像头已更新");
      mutation.reset();
      setOpen(false);
      onClosed();
    } catch (error: unknown) {
      try {
        applyMutationFailure(error);
      } finally {
        // 错误已转换为固定 UI 状态后立即移除携带当前密码和 Source 后缀的 Mutation variables。
        mutation.reset();
      }
    }
  }

  async function submit(values: ValidatedCameraEditFormValues) {
    if (formAlert?.kind === "unknown") {
      setConfirmation("retry");
      return;
    }
    await submitRequest(values);
  }

  const activeConfirmation =
    confirmation ??
    (blocker.status === "blocked" && open && isDirty && !isSubmitting
      ? "discard-navigation"
      : undefined);

  function cancelConfirmation() {
    if (activeConfirmation === "discard-navigation") {
      blocker.reset?.();
    }
    setConfirmation(undefined);
  }

  function confirmAction() {
    if (activeConfirmation === "retry") {
      setConfirmation(undefined);
      void form.handleSubmit(submitRequest)();
      return;
    }
    if (activeConfirmation === "discard-navigation") {
      resetDialogState();
      setOpen(false);
      blocker.proceed?.();
      return;
    }
    closeDialog();
  }

  const isRetryConfirmation = activeConfirmation === "retry";

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      disablePointerDismissal={isSubmitting}
    >
      <DialogContent
        className="max-h-[calc(100svh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden sm:max-w-2xl"
        showCloseButton={!isSubmitting}
      >
        <DialogHeader className="pr-8">
          <DialogTitle>编辑摄像头</DialogTitle>
          <DialogDescription>
            更新连接信息、视频源顺序和默认预览源。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="-mx-4 min-h-0">
          {/* Ring 需要在 ScrollArea viewport 内保留横向空间，否则聚焦边框会被裁切。 */}
          <form
            id={formId}
            className="flex flex-col gap-5 px-4 pb-1"
            onSubmit={(event) => {
              void form.handleSubmit(submit)(event);
            }}
            noValidate
          >
            {formAlert === undefined ? null : (
              <Alert
                variant={formAlert.kind === "error" ? "destructive" : "default"}
                aria-live="assertive"
              >
                <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
                <AlertTitle>{formAlert.title}</AlertTitle>
                <AlertDescription>
                  {formAlert.messages.map((message) => (
                    <p key={message}>{message}</p>
                  ))}
                </AlertDescription>
              </Alert>
            )}

            <CameraConnectionFields
              formId={formId}
              registrations={{
                name: form.register("name"),
                ip_address: form.register("ip_address"),
                rtsp_port: form.register("rtsp_port", {
                  valueAsNumber: true,
                }),
                username: form.register("username"),
                password: form.register("password"),
              }}
              errors={{
                name: fieldErrorMessage(form.formState.errors.name?.message),
                ip_address: fieldErrorMessage(
                  form.formState.errors.ip_address?.message,
                ),
                rtsp_port: fieldErrorMessage(
                  form.formState.errors.rtsp_port?.message,
                ),
                username: fieldErrorMessage(
                  form.formState.errors.username?.message,
                ),
                password: fieldErrorMessage(
                  form.formState.errors.password?.message,
                ),
              }}
              disabled={isSubmitting}
              passwordAutoComplete="current-password"
            />

            <Separator />

            <CameraEditSourceFields
              formId={formId}
              fields={fields}
              sources={watchedSources}
              register={form.register}
              errors={form.formState.errors}
              defaultSourceFieldId={defaultSourceFieldId}
              disabled={isSubmitting}
              onAddSource={() => append(createEmptyCameraEditSource(false))}
              onRemoveSource={removeSource}
              onMoveSource={move}
              onDefaultSourceChange={setDefaultSource}
            />
          </form>
        </ScrollArea>

        <DialogFooter>
          <DialogClose
            render={<Button type="button" variant="outline" />}
            disabled={isSubmitting}
          >
            取消
          </DialogClose>
          <Button type="submit" form={formId} disabled={isSubmitting}>
            {isSubmitting ? (
              <Spinner data-icon="inline-start" aria-label="正在保存摄像头" />
            ) : null}
            {isSubmitting ? "正在保存…" : "保存修改"}
          </Button>
        </DialogFooter>
      </DialogContent>

      <AlertDialog
        open={activeConfirmation !== undefined}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            cancelConfirmation();
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {isRetryConfirmation ? "再次发送完整更新？" : "丢弃未保存修改？"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {isRetryConfirmation
                ? "上一请求可能已经保存。本次确认会使用当前表单再发送一条完整更新，并可能覆盖服务端较新的配置。"
                : "当前表单中的修改将丢失，且无法恢复。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {isRetryConfirmation ? "暂不发送" : "留下继续编辑"}
            </AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmAction}>
              {isRetryConfirmation ? "确认再次保存" : "确认丢弃"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
