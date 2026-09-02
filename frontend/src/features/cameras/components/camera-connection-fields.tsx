import type { UseFormRegisterReturn } from "react-hook-form";

import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

type CameraConnectionFieldName =
  "name" | "ip_address" | "rtsp_port" | "username" | "password";

type CameraConnectionRegistrations = {
  readonly name: UseFormRegisterReturn<"name">;
  readonly ip_address: UseFormRegisterReturn<"ip_address">;
  readonly rtsp_port: UseFormRegisterReturn<"rtsp_port">;
  readonly username: UseFormRegisterReturn<"username">;
  readonly password: UseFormRegisterReturn<"password">;
};

interface CameraConnectionFieldsProps {
  readonly formId: string;
  readonly registrations: CameraConnectionRegistrations;
  readonly errors: Readonly<
    Record<CameraConnectionFieldName, string | undefined>
  >;
  readonly disabled: boolean;
  readonly passwordAutoComplete: "current-password" | "new-password";
}

/**
 * 创建和编辑共用的连接字段视图。
 *
 * 调用方传入已经绑定到自己 DTO 的注册结果，因此该组件不会让 Create 表单接受 Update Source 字段，
 * 也不会创建第二份 React Hook Form 状态。
 */
export function CameraConnectionFields({
  formId,
  registrations,
  errors,
  disabled,
  passwordAutoComplete,
}: CameraConnectionFieldsProps) {
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
          data-camera-form-field="name"
          {...registrations.name}
        />
        <FieldError>{errors.name}</FieldError>
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
          data-camera-form-field="ip_address"
          {...registrations.ip_address}
        />
        <FieldError>{errors.ip_address}</FieldError>
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
          data-camera-form-field="rtsp_port"
          {...registrations.rtsp_port}
        />
        <FieldError>{errors.rtsp_port}</FieldError>
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
          data-camera-form-field="username"
          {...registrations.username}
        />
        <FieldError>{errors.username}</FieldError>
      </Field>

      <Field
        data-invalid={errors.password !== undefined}
        data-disabled={disabled}
      >
        <FieldLabel htmlFor={`${formId}-password`}>密码</FieldLabel>
        <Input
          id={`${formId}-password`}
          type="password"
          autoComplete={passwordAutoComplete}
          disabled={disabled}
          aria-invalid={errors.password !== undefined}
          data-camera-form-field="password"
          {...registrations.password}
        />
        <FieldError>{errors.password}</FieldError>
      </Field>
    </FieldGroup>
  );
}
