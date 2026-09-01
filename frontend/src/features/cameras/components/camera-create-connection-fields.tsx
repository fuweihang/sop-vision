import type { FieldErrors, UseFormRegister } from "react-hook-form";

import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { fieldErrorMessage } from "@/features/cameras/forms/camera-create-error-mapping";
import type { CameraCreateFormValues } from "@/features/cameras/forms/camera-create-form";

interface CameraCreateConnectionFieldsProps {
  readonly formId: string;
  readonly register: UseFormRegister<CameraCreateFormValues>;
  readonly errors: FieldErrors<CameraCreateFormValues>;
  readonly disabled: boolean;
}

/**
 * Camera 连接字段只负责渲染和注册控件。
 *
 * 表单生命周期、提交和错误分类仍由父 Dialog 管理；这里接收显式依赖，避免子组件创建第二份表单
 * 状态。凭据字段保持原 autocomplete 和错误展示方式，不在组件内读取或复制用户输入。
 */
export function CameraCreateConnectionFields({
  formId,
  register,
  errors,
  disabled,
}: CameraCreateConnectionFieldsProps) {
  return (
    <FieldGroup className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2">
      <Field
        className="sm:col-span-2"
        data-invalid={errors.name !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-name`}>摄像头名称</FieldLabel>
        <Input
          id={`${formId}-name`}
          placeholder="例如：洗手区 01"
          autoComplete="off"
          disabled={disabled}
          aria-invalid={errors.name !== undefined}
          data-camera-create-field="name"
          {...register("name")}
        />
        <FieldError>{fieldErrorMessage(errors.name?.message)}</FieldError>
      </Field>

      <Field
        data-invalid={errors.ip_address !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-ip-address`}>IP 地址</FieldLabel>
        <Input
          id={`${formId}-ip-address`}
          inputMode="decimal"
          autoComplete="off"
          disabled={disabled}
          aria-invalid={errors.ip_address !== undefined}
          data-camera-create-field="ip_address"
          {...register("ip_address")}
        />
        <FieldError>{fieldErrorMessage(errors.ip_address?.message)}</FieldError>
      </Field>

      <Field
        data-invalid={errors.rtsp_port !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-rtsp-port`}>RTSP 端口</FieldLabel>
        <Input
          id={`${formId}-rtsp-port`}
          type="number"
          min={1}
          max={65535}
          inputMode="numeric"
          autoComplete="off"
          disabled={disabled}
          aria-invalid={errors.rtsp_port !== undefined}
          data-camera-create-field="rtsp_port"
          {...register("rtsp_port", { valueAsNumber: true })}
        />
        <FieldError>{fieldErrorMessage(errors.rtsp_port?.message)}</FieldError>
      </Field>

      <Field
        data-invalid={errors.username !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-username`}>用户名</FieldLabel>
        <Input
          id={`${formId}-username`}
          autoComplete="username"
          disabled={disabled}
          aria-invalid={errors.username !== undefined}
          data-camera-create-field="username"
          {...register("username")}
        />
        <FieldError>{fieldErrorMessage(errors.username?.message)}</FieldError>
      </Field>

      <Field
        data-invalid={errors.password !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-password`}>密码</FieldLabel>
        <Input
          id={`${formId}-password`}
          type="password"
          autoComplete="new-password"
          disabled={disabled}
          aria-invalid={errors.password !== undefined}
          data-camera-create-field="password"
          {...register("password")}
        />
        <FieldError>{fieldErrorMessage(errors.password?.message)}</FieldError>
      </Field>
    </FieldGroup>
  );
}
