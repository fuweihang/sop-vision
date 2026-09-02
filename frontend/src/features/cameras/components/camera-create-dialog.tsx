import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon, Alert02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AxiosInstance } from "axios";
import { useId, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { createCamera } from "@/features/cameras/api/cameras-api";
import { CameraConnectionFields } from "@/features/cameras/components/camera-connection-fields";
import { CameraCreateSourceFields } from "@/features/cameras/components/camera-create-source-fields";
import {
  mapCameraCreateFailure,
  type CameraCreateFieldName,
  type CameraCreateFormAlert,
} from "@/features/cameras/forms/camera-create-error-mapping";
import {
  CAMERA_CREATE_DEFAULT_VALUES,
  cameraCreateFormSchema,
  createEmptyCameraSource,
  toCameraCreateRequest,
  type CameraCreateFormValues,
  type ValidatedCameraCreateFormValues,
} from "@/features/cameras/forms/camera-create-form";
import { fieldErrorMessage } from "@/features/cameras/forms/camera-form-errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";

interface CameraCreateDialogProps {
  apiClient: AxiosInstance;
}

/** Camera 创建表单；只保留当前 Dialog 所需状态，不建立跨页面草稿或详情缓存。 */
export function CameraCreateDialog({ apiClient }: CameraCreateDialogProps) {
  const formId = useId();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [formAlert, setFormAlert] = useState<CameraCreateFormAlert>();
  const form = useForm<
    CameraCreateFormValues,
    unknown,
    ValidatedCameraCreateFormValues
  >({
    resolver: zodResolver(cameraCreateFormSchema),
    defaultValues: CAMERA_CREATE_DEFAULT_VALUES,
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
    mutationFn: async (request: ReturnType<typeof toCameraCreateRequest>) => {
      // CameraDetail 含凭据和完整 RTSP URL。调用只需要知道请求成功，不把响应返回给
      // TanStack Mutation Cache，避免 Dialog 关闭后继续保留一份无 UI 用途的敏感详情。
      await createCamera(request, apiClient);
    },
    retry: false,
    // reset 后立即回收携带写请求变量的 mutation；用户草稿由 React Hook Form 单独保留。
    gcTime: 0,
  });
  const isSubmitting = form.formState.isSubmitting;
  const defaultSourceFieldId = fields.find(
    (_field, index) => watchedSources[index]?.is_default_preview,
  )?.id;

  function resetDialog() {
    form.reset(CAMERA_CREATE_DEFAULT_VALUES);
    form.clearErrors();
    setFormAlert(undefined);
    mutation.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    // 数据库提交结果可能已经不可逆。提交期间拒绝 Escape、外部点击和关闭按钮，避免用户误以为
    // 取消 Dialog 就取消了正在进行的创建请求。
    if (!nextOpen && isSubmitting) {
      return;
    }
    setOpen(nextOpen);
    if (!nextOpen) {
      resetDialog();
    }
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
      // 删除后 React Hook Form 会同步移动数组；默认选中新的第 0 项，保持“始终恰好一路默认”。
      form.setValue("sources.0.is_default_preview", true, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }

  function focusMappedField(fieldName: CameraCreateFieldName) {
    requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(
        `[data-camera-form-field="${fieldName}"], [data-camera-create-field="${fieldName}"]`,
      );
      target?.focus();
    });
  }

  function handleMutationError(error: unknown) {
    const failure = mapCameraCreateFailure(error, fields.length);
    if (failure.kind === "alert") {
      setFormAlert(failure.formAlert);
      return;
    }

    form.clearErrors();
    for (const fieldError of failure.fieldErrors) {
      form.setError(fieldError.fieldName, {
        type: "server",
        message: fieldError.message,
      });
    }
    setFormAlert(failure.formAlert);

    const firstFocusableField = failure.fieldErrors[0]?.fieldName;
    if (firstFocusableField !== undefined) {
      focusMappedField(firstFocusableField);
    }
  }

  async function submit(values: ValidatedCameraCreateFormValues) {
    if (formAlert?.kind !== "unknown") {
      setFormAlert(undefined);
    }

    try {
      await mutation.mutateAsync(toCameraCreateRequest(values));
      await queryClient.invalidateQueries({ queryKey: ["cameras"] });
      toast.success("摄像头已创建");
      setOpen(false);
      resetDialog();
    } catch (error: unknown) {
      try {
        handleMutationError(error);
      } finally {
        // Mutation 会保存 variables 和响应，其中包含凭据。错误已经转换为不含原始 Axios 请求的
        // 安全类型后立即 reset，只把用户仍可见的表单草稿保留在 React Hook Form 中。
        mutation.reset();
      }
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      disablePointerDismissal={isSubmitting}
    >
      <DialogTrigger render={<Button />}>
        <HugeiconsIcon
          icon={Add01Icon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        添加摄像头
      </DialogTrigger>
      <DialogContent
        className="max-h-[calc(100svh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden sm:max-w-2xl"
        showCloseButton={!isSubmitting}
      >
        <DialogHeader className="pr-8">
          <DialogTitle>添加摄像头</DialogTitle>
          <DialogDescription>
            保存设备连接信息和至少一路视频源。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="-mx-4 min-h-0">
          {/* 留白必须放在 ScrollArea viewport 内部；放在 Root 上会让输入框贴住 viewport，
              聚焦时向外扩展的 3px Ring 会被滚动容器裁掉。 */}
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
              passwordAutoComplete="new-password"
            />

            <Separator />

            <CameraCreateSourceFields
              formId={formId}
              fields={fields}
              sources={watchedSources}
              register={form.register}
              errors={form.formState.errors}
              defaultSourceFieldId={defaultSourceFieldId}
              disabled={isSubmitting}
              onAddSource={() => append(createEmptyCameraSource(false))}
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
            {isSubmitting ? "正在保存…" : "保存摄像头"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
